"""Bench device simulator. No database and no production capture."""

import socket
import struct

import pytest

from astra.cli.device import iter_datagrams, main, synthetic_datagram, timer_step_ms
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
