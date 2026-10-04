import struct

from astra.bridge import DeviceRow, accept_datagram, bridge_port
from astra.bridge.__main__ import main
from astra.opcua import DEFAULT_ENDPOINT, endpoint, tag_path


def test_bridge_entrypoint_uses_opcua_tags() -> None:
    assert bridge_port({}) == 2357
    assert bridge_port({"ASTRA_BRIDGE_PORT": "2400"}) == 2400
    assert endpoint({}) == DEFAULT_ENDPOINT
    assert tag_path("R2L", "t_ms") == "AstraR2L/t_ms"
    assert main(["--check"]) == 0


def test_bridge_accepts_only_a_strictly_newer_t_ms() -> None:
    devices = {4: DeviceRow(payload_size=5, peer_ip="10.0.0.8")}
    payload = struct.pack("<i", 1000) + b"\x5a"
    assert accept_datagram(9, payload, "10.0.0.8", devices, 0) is None
    assert accept_datagram(4, payload + b"\x00", "10.0.0.8", devices, 0) is None
    assert accept_datagram(4, payload, "10.0.0.9", devices, 0) is None
    assert accept_datagram(4, payload, "10.0.0.8", devices, 1000) is None
    assert accept_datagram(4, payload, "10.0.0.8", devices, 1001) is None
    assert accept_datagram(4, struct.pack("<i", -4) + b"\x00", "10.0.0.8", devices, -5) == -4
    assert accept_datagram(4, payload, "10.0.0.8", devices, 999) == 1000
