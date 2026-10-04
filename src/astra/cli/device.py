"""Bench UDP peer.

``AstraDevice`` is a timer, not a service. This tool sends synthetic R2L
datagrams: a signed int32 packet id, then a payload whose first four bytes
are ``t_ms``. ``t_ms`` starts at the timer interval and increases by that
interval. The interval is ``round(1000 / rate)`` milliseconds, at least 1.
The rest of the payload is zeros. Nothing here opens the database.

``--count`` defaults to 1. ``--count 0`` sends until interrupted. Sends are
scheduled on a monotonic deadline so the pause is the time left in the
step, not a full sleep after the work. Replies already queued are drained
and printed as a byte count. A quiet peer does not add a wait.
"""

from __future__ import annotations

import argparse
import select
import socket
import sys
import time
from collections.abc import Iterator

from astra.codec.errors import CodecError
from astra.codec.framing import pack_id_payload
from astra.settings import bridge_port

_INT32_MIN = -0x80000000
_INT32_MAX = 0x7FFFFFFF
_MIN_PAYLOAD = 4
_MAX_PAYLOAD = 65503
_MAX_RATE_HZ = 1000
_MAX_COUNT = 1_000_000


def timer_step_ms(rate_hz: int) -> int:
    """Return the ``t_ms`` step for a send rate in hertz."""
    if isinstance(rate_hz, bool) or not isinstance(rate_hz, int):
        raise ValueError("rate must be an integer from 1 to 1000")
    if rate_hz < 1 or rate_hz > _MAX_RATE_HZ:
        raise ValueError("rate must be an integer from 1 to 1000")
    return max(1, round(1000 / rate_hz))


def synthetic_datagram(packet_id: int, payload_size: int, t_ms: int) -> bytes:
    """Return one datagram with ``t_ms`` in the first four payload bytes."""
    if isinstance(payload_size, bool) or not isinstance(payload_size, int):
        raise ValueError("size must be an integer from 4 to 65503")
    if payload_size < _MIN_PAYLOAD or payload_size > _MAX_PAYLOAD:
        raise ValueError("size must be an integer from 4 to 65503")
    if isinstance(t_ms, bool) or not isinstance(t_ms, int):
        raise ValueError("t_ms does not fit in a signed 32-bit integer")
    if t_ms < _INT32_MIN or t_ms > _INT32_MAX:
        raise ValueError("t_ms does not fit in a signed 32-bit integer")
    payload = t_ms.to_bytes(4, "little", signed=True) + bytes(payload_size - 4)
    try:
        return pack_id_payload(packet_id, payload)
    except CodecError as exc:
        raise ValueError(str(exc)) from exc


def iter_datagrams(
    packet_id: int,
    payload_size: int,
    rate_hz: int,
    count: int,
) -> Iterator[tuple[int, bytes]]:
    """Yield ``(t_ms, datagram)`` for ``count`` sends. ``count`` 0 does not stop."""
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("count must be an integer from 0 to 1000000")
    if count > _MAX_COUNT:
        raise ValueError("count must be an integer from 0 to 1000000")
    step = timer_step_ms(rate_hz)
    sent = 0
    t_ms = 0
    while count == 0 or sent < count:
        t_ms += step
        if t_ms > _INT32_MAX:
            raise ValueError("t_ms does not fit in a signed 32-bit integer")
        yield t_ms, synthetic_datagram(packet_id, payload_size, t_ms)
        sent += 1


def send_datagrams(
    packet_id: int,
    payload_size: int,
    rate_hz: int,
    count: int,
    host: str,
    port: int,
    *,
    pause: bool = True,
) -> int:
    """Send the sequence. Return 0, or 1 when a datagram cannot be sent.

    The first datagram goes out immediately. Send ``n`` is due at
    ``start + n * step``. Time spent printing or reading replies comes out
    of that step instead of being added to it.
    """
    step_s = timer_step_ms(rate_hz) / 1000
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            started = time.monotonic()
            frames = enumerate(iter_datagrams(packet_id, payload_size, rate_hz, count))
            for index, (t_ms, datagram) in frames:
                if pause and index > 0:
                    delay = started + index * step_s - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)
                try:
                    sock.sendto(datagram, (host, port))
                except OSError:
                    print("could not send", file=sys.stderr)
                    return 1
                print(f"sent packet_id={packet_id} t_ms={t_ms} size={payload_size}", flush=True)
                _drain_replies(sock)
    except KeyboardInterrupt:
        return 0
    return 0


def _drain_replies(sock: socket.socket) -> None:
    """Print every reply already queued. A zero timeout does not wait."""
    while True:
        try:
            ready = select.select([sock], [], [], 0)[0]
        except OSError:
            return
        if not ready:
            return
        try:
            data = sock.recv(65535)
        except (TimeoutError, OSError):
            return
        print(f"recv {len(data)} bytes", flush=True)


def _host(value: str) -> str:
    host = value.strip()
    if host == "" or len(host) > 253 or any(ord(char) < 33 for char in host):
        raise ValueError("host is not usable")
    return host


def _bounded(name: str, value: int | None, minimum: int, maximum: int) -> int:
    if value is None:
        raise ValueError(f"{name} is required")
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum or value > maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m astra.cli.device",
        description="Send synthetic R2L datagrams to the bridge.",
    )
    parser.add_argument("--check", action="store_true", help="Exit without sending")
    parser.add_argument("--packet-id", type=int)
    parser.add_argument("--size", type=int, help="Payload bytes, including the 4-byte t_ms")
    parser.add_argument("--rate", type=int, help="Sends per second, from 1 to 1000")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int)
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Datagrams to send; 0 runs until interrupted",
    )
    args = parser.parse_args(argv)
    if args.check:
        return 0
    try:
        packet_id = _bounded("packet-id", args.packet_id, _INT32_MIN, _INT32_MAX)
        payload_size = _bounded("size", args.size, _MIN_PAYLOAD, _MAX_PAYLOAD)
        rate_hz = _bounded("rate", args.rate, 1, _MAX_RATE_HZ)
        port = bridge_port() if args.port is None else _bounded("port", args.port, 1, 65535)
        count = _bounded("count", args.count, 0, _MAX_COUNT)
        host = _host(args.host)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    return send_datagrams(packet_id, payload_size, rate_hz, count, host, port)


if __name__ == "__main__":
    raise SystemExit(main())
