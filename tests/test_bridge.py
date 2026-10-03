from astra_ground_station.bridge import DEFAULT_ENDPOINT, opcua_endpoint, opcua_library_version
from astra_ground_station.bridge.__main__ import main


def test_bridge_entrypoint_and_endpoint() -> None:
    assert opcua_library_version() != "unknown"
    assert opcua_endpoint({}) == DEFAULT_ENDPOINT
    assert opcua_endpoint({"ASTRA_OPCUA_ENDPOINT": "opc.tcp://127.0.0.1:4841/"}) == (
        "opc.tcp://127.0.0.1:4841/"
    )
    assert main(["--check"]) == 0
