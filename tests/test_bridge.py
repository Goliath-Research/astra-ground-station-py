from astra.bridge import bridge_port
from astra.bridge.__main__ import main
from astra.opcua import DEFAULT_ENDPOINT, endpoint, tag_path


def test_bridge_entrypoint_uses_opcua_tags() -> None:
    assert bridge_port({}) == 2357
    assert bridge_port({"ASTRA_BRIDGE_PORT": "2400"}) == 2400
    assert endpoint({}) == DEFAULT_ENDPOINT
    assert tag_path("R2L", "t_ms") == "AstraR2L/t_ms"
    assert main(["--check"]) == 0
