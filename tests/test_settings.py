import pytest

from astra.settings import (
    DEFAULT_BRIDGE_PORT,
    DEFAULT_STAGE_COUNT,
    SettingsError,
    bridge_port,
    stage_count,
    stage_port,
    stage_ports,
)


def test_defaults_match_the_legacy_literals() -> None:
    assert bridge_port({}) == DEFAULT_BRIDGE_PORT == 2357
    assert stage_count({}) == DEFAULT_STAGE_COUNT == 2
    assert stage_ports({}) == (2358, 2359)


def test_blank_values_use_the_defaults() -> None:
    environ = {"ASTRA_BRIDGE_PORT": "  ", "ASTRA_STAGE_COUNT": ""}
    assert bridge_port(environ) == 2357
    assert stage_count(environ) == 2


def test_env_overrides_port_and_stage_count() -> None:
    environ = {"ASTRA_BRIDGE_PORT": "2400", "ASTRA_STAGE_COUNT": "3"}
    assert bridge_port(environ) == 2400
    assert stage_count(environ) == 3
    assert stage_port(1, environ) == 2401
    assert stage_ports(environ) == (2401, 2402, 2403)


def test_rejects_unusable_configuration() -> None:
    with pytest.raises(SettingsError, match="ASTRA_BRIDGE_PORT"):
        bridge_port({"ASTRA_BRIDGE_PORT": "2357x"})
    with pytest.raises(SettingsError, match="ASTRA_BRIDGE_PORT"):
        bridge_port({"ASTRA_BRIDGE_PORT": "0"})
    with pytest.raises(SettingsError, match="ASTRA_STAGE_COUNT"):
        stage_count({"ASTRA_STAGE_COUNT": "0"})
    with pytest.raises(SettingsError, match="stage"):
        stage_port(3, {})
    with pytest.raises(SettingsError, match="65535"):
        stage_port(1, {"ASTRA_BRIDGE_PORT": "65535", "ASTRA_STAGE_COUNT": "1"})
