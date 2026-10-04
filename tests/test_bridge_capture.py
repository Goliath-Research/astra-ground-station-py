"""Localhost recorder. Rejected datagrams stay out of the log."""

import socket
import struct
from datetime import datetime
from pathlib import Path

from astra.bridge import DeviceRow
from astra.bridge.capture import LocalRecorder, replay_payloads
from astra.cli.device import main as device_main
from astra.codec.framing import device_t_ms, pack_id_payload


def _payload(t_ms: int, size: int = 8) -> bytes:
    return struct.pack("<i", t_ms) + bytes(size - 4)


def test_simulator_datagrams_are_recorded_and_replayed(tmp_path: Path) -> None:
    moment = datetime(2026, 1, 2, 3, 4, 5)
    devices = {4: DeviceRow(payload_size=8, peer_ip="127.0.0.1")}
    with LocalRecorder(devices, test_id=7, directory=tmp_path, clock=lambda: moment) as recorder:
        code = device_main(
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
                str(recorder.port),
                "--count",
                "2",
            ]
        )
        assert code == 0
        assert recorder.take() is True
        assert recorder.take() is True
        path = recorder.paths[4]
    payloads = replay_payloads(path)
    assert [device_t_ms(payload) for payload in payloads] == [1, 2]
    assert path.name == "LOG-T7-I4.DAT"


def test_rejected_datagrams_are_not_recorded(tmp_path: Path) -> None:
    devices = {4: DeviceRow(payload_size=8, peer_ip="127.0.0.1")}
    with LocalRecorder(devices, test_id=7, directory=tmp_path) as recorder:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            target = ("127.0.0.1", recorder.port)
            sender.sendto(pack_id_payload(4, _payload(50)), target)
            sender.sendto(pack_id_payload(4, _payload(60, size=5)), target)
            sender.sendto(pack_id_payload(4, _payload(50)), target)
            sender.sendto(pack_id_payload(9, _payload(70)), target)
        assert recorder.take() is True
        assert recorder.take() is False
        assert recorder.take() is False
        assert recorder.take() is False
        assert recorder.consider(pack_id_payload(4, _payload(80)), "10.0.0.9") is False
        path = recorder.paths[4]
    assert [device_t_ms(payload) for payload in replay_payloads(path)] == [50]
