"""Localhost bridge receive path.

Binds ``127.0.0.1``, applies :func:`astra.bridge.accept_datagram`, and appends
each accepted payload to ``LOG-T{test}-I{packet}.DAT``. A rejected datagram
is not written. :func:`replay_payloads` reads that file back.
"""

from __future__ import annotations

import socket
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from astra.binlog import dat_filename, header_bytes, ole_days, read_dat, record_bytes
from astra.bridge import DeviceRow, accept_datagram
from astra.codec.errors import CodecError
from astra.codec.framing import device_t_ms, unpack_id_payload

Clock = Callable[[], datetime]


class LocalRecorder:
    """One UDP socket and the logs it accepts."""

    def __init__(
        self,
        devices: Mapping[int, DeviceRow],
        *,
        test_id: int,
        directory: Path,
        clock: Clock | None = None,
    ) -> None:
        self._devices = devices
        self._test_id = test_id
        self._directory = directory
        self._clock = datetime.now if clock is None else clock
        self._last: dict[int, int] = {}
        self._handles: dict[int, BinaryIO] = {}
        self.paths: dict[int, Path] = {}
        directory.mkdir(parents=True, exist_ok=True)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.settimeout(2)
        port = self._sock.getsockname()[1]
        if not isinstance(port, int):
            raise RuntimeError("udp port is not an int")
        self.port = port

    def __enter__(self) -> LocalRecorder:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._sock.close()
        for handle in self._handles.values():
            handle.close()
        self._handles.clear()

    def take(self) -> bool:
        """Receive one datagram. Return whether it was written."""
        data, addr = self._sock.recvfrom(65535)
        peer = addr[0]
        if not isinstance(peer, str):
            return False
        return self.consider(data, peer)

    def consider(self, data: bytes, peer_ip: str) -> bool:
        """Apply the accept rules and append a payload when they pass."""
        try:
            packet_id, payload = unpack_id_payload(data)
        except CodecError:
            return False
        last = self._last.get(packet_id, 0)
        accepted = accept_datagram(packet_id, payload, peer_ip, self._devices, last)
        if accepted is None:
            return False
        self._last[packet_id] = accepted
        self._append(packet_id, payload)
        return True

    def _append(self, packet_id: int, payload: bytes) -> None:
        opened = self._handles.get(packet_id)
        if opened is None:
            path = self._directory / dat_filename(self._test_id, packet_id)
            opened = path.open("wb")
            opened.write(header_bytes(self._test_id, packet_id, len(payload)))
            self._handles[packet_id] = opened
            self.paths[packet_id] = path
        stamp = ole_days(self._clock())
        opened.write(record_bytes(stamp, payload, len(payload)))
        opened.flush()


def replay_payloads(path: Path) -> tuple[bytes, ...]:
    """Return accepted payloads. ``t_ms`` must keep increasing."""
    log = read_dat(path)
    last: int | None = None
    payloads: list[bytes] = []
    for record in log.records:
        try:
            t_ms = device_t_ms(record.payload)
        except CodecError as exc:
            raise ValueError("payload has no t_ms") from exc
        if last is not None and t_ms <= last:
            raise ValueError("t_ms does not increase")
        last = t_ms
        payloads.append(record.payload)
    return tuple(payloads)
