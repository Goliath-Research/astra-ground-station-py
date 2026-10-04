"""Process configuration from the environment.

``/etc/astra/astra.env`` is the config file. systemd loads it with
``EnvironmentFile=``, so a key written there is the value the process reads.
Legacy Delphi literals are defaults only.
"""

import os
from collections.abc import Mapping

DEFAULT_BRIDGE_PORT = 2357  # config.servers.port; device ports default to this
DEFAULT_STAGE_COUNT = 2
_MAX_UDP_PORT = 65535


class SettingsError(ValueError):
    """An Astra environment value is present and not usable."""


def bridge_port(environ: Mapping[str, str] | None = None) -> int:
    """Return the bridge UDP port.

    ``ASTRA_BRIDGE_PORT`` overrides the legacy default of 2357. TMoIP listens
    on this port plus the stage number and forwards reassembled datagrams
    back to this port.
    """
    return _configured_int(
        environ,
        "ASTRA_BRIDGE_PORT",
        DEFAULT_BRIDGE_PORT,
        maximum=_MAX_UDP_PORT,
    )


def stage_count(environ: Mapping[str, str] | None = None) -> int:
    """Return how many stages to decode.

    ``ASTRA_STAGE_COUNT`` overrides the default of 2. The first vehicle had
    two stages; a different count is a configuration change.
    """
    return _configured_int(environ, "ASTRA_STAGE_COUNT", DEFAULT_STAGE_COUNT)


def stage_port(stage: int, environ: Mapping[str, str] | None = None) -> int:
    """Return the UDP port for one stage decoder.

    Stage numbers start at 1. The port is ``bridge_port + stage``.
    """
    if isinstance(stage, bool) or not isinstance(stage, int) or stage < 1:
        raise SettingsError(f"stage must be an integer >= 1, got {stage!r}")
    count = stage_count(environ)
    if stage > count:
        raise SettingsError(f"stage {stage} is above ASTRA_STAGE_COUNT {count}")
    port = bridge_port(environ) + stage
    if port > _MAX_UDP_PORT:
        raise SettingsError(f"stage {stage} port {port} is above {_MAX_UDP_PORT}")
    return port


def stage_ports(environ: Mapping[str, str] | None = None) -> tuple[int, ...]:
    """Return decoder ports for stages 1 through ``stage_count``."""
    count = stage_count(environ)
    return tuple(stage_port(stage, environ) for stage in range(1, count + 1))


def _configured_int(
    environ: Mapping[str, str] | None,
    name: str,
    default: int,
    *,
    maximum: int | None = None,
) -> int:
    env = os.environ if environ is None else environ
    raw = env.get(name, "").strip()
    if not raw:
        value = default
    else:
        try:
            value = int(raw, 10)
        except ValueError as exc:
            raise SettingsError(f"{name} must be an integer, got {raw!r}") from exc
    if value < 1 or (maximum is not None and value > maximum):
        limit = f"1..{maximum}" if maximum is not None else ">= 1"
        raise SettingsError(f"{name} must be {limit}, got {value}")
    return value
