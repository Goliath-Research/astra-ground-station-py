"""Bench device simulator. No database and no production capture."""

import socket
import struct
import time

import pytest

from astra.cli.device import _drain_replies, iter_datagrams, main, synthetic_datagram, timer_step_ms
from astra.codec.framing import unpack_id_payload


def test_timer_step_follows_the_rate() -> None:
    assert timer_step_ms(10) == 100
    assert timer_step_ms(1000) == 1
    assert timer_step_ms(3) == 333


def test_datagrams_step_t_ms_and_prefix_the_packet_id() -> None:
    frames = list(iter_datagrams(4, 8, 10, 3))
    assert [item[0] for item in frames] == [100, 200, 300]
    for t_ms, datagram in frames:
        packet_id, payload = unpack_id_payload(datagram)
        assert packet_id == 4
        assert len(payload) == 8
        assert struct.unpack_from("<i", payload)[0] == t_ms
        assert payload[4:] == bytes(4)


def test_payload_rejects_a_short_size() -> None:
    with pytest.raises(ValueError, match="size"):
        synthetic_datagram(1, 3, 0)


def test_missing_arguments_exit_2() -> None:
    assert main([]) == 2
    assert main(["--packet-id", "4", "--size", "8"]) == 2


def test_check_does_not_send() -> None:
    assert main(["--check"]) == 0


def test_sends_two_datagrams_to_localhost() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind(("127.0.0.1", 0))
        server.settimeout(2)
        port = server.getsockname()[1]
        assert isinstance(port, int)
        code = main(
            [
                "--packet-id",
                "4",
                "--size",
                "8",
                "--rate",
                "1000",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--count",
                "2",
            ]
        )
        assert code == 0
        first, _ = server.recvfrom(64)
        second, _ = server.recvfrom(64)
    assert unpack_id_payload(first)[0] == 4
    assert struct.unpack_from("<i", unpack_id_payload(first)[1])[0] == 1
    assert struct.unpack_from("<i", unpack_id_payload(second)[1])[0] == 2


def test_empty_reply_queue_does_not_wait() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        started = time.monotonic()
        _drain_replies(sock)
        elapsed = time.monotonic() - started
    assert elapsed < 0.05


def test_queued_replies_are_drained(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as peer,
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock,
    ):
        peer.bind(("127.0.0.1", 0))
        sock.bind(("127.0.0.1", 0))
        peer.sendto(b"aa", sock.getsockname())
        peer.sendto(b"bbb", sock.getsockname())
        started = time.monotonic()
        _drain_replies(sock)
        elapsed = time.monotonic() - started
    captured = capsys.readouterr()
    assert "recv 2 bytes" in captured.out
    assert "recv 3 bytes" in captured.out
    assert elapsed < 0.05


def test_send_pace_is_not_stretched_by_a_reply_wait() -> None:
    """31 sends at 1000 Hz are 30 ms of gaps. A 10 ms recv wait would be ~300 ms."""
    count = 31
    expected = (count - 1) * timer_step_ms(1000) / 1000
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind(("127.0.0.1", 0))
        server.settimeout(2)
        port = server.getsockname()[1]
        assert isinstance(port, int)
        started = time.monotonic()
        code = main(
            [
                "--packet-id",
                "4",
                "--size",
                "8",
                "--rate",
                "1000",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--count",
                str(count),
            ]
        )
        elapsed = time.monotonic() - started
        for _ in range(count):
            server.recvfrom(64)
    assert code == 0
    assert elapsed > expected * 0.5
    assert elapsed < 0.15
