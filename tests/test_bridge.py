from astra.bridge.__main__ import main
from astra.opcua import DEFAULT_ENDPOINT, endpoint, tag_path


def test_bridge_entrypoint_uses_opcua_tags() -> None:
    assert endpoint({}) == DEFAULT_ENDPOINT
    assert tag_path("R2L", "t_ms") == "AstraR2L/t_ms"
    assert main(["--check"]) == 0
