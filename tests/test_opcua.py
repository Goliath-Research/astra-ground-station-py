from astra.opcua import library_version, tag_path


def test_asyncua_is_the_server_library() -> None:
    assert library_version() != "unknown"
    assert tag_path("L2R", "command") == "AstraL2R/command"
