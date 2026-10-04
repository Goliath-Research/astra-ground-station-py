"""OPC UA server embedded in the bridge.

LabVIEW subscribes to tags this process publishes. The server is not started.
Tag paths replace ``\\\\.\\Astra{PacketName}\\{field}`` with
``Astra{PacketName}/{field}``.
"""

import os
from collections.abc import Mapping

import asyncua

DEFAULT_ENDPOINT = "opc.tcp://0.0.0.0:4840/astra/"
# config.servers OPC DA ProgID. Legacy reference only; the bridge publishes
# OPC UA at ``ASTRA_OPCUA_ENDPOINT`` and does not connect to this name.
LEGACY_OPC_DA_SERVER = "National Instruments.Variable Engine.1"


def library_version() -> str:
    """Return the installed asyncua version."""
    version = asyncua.__version__
    if isinstance(version, str) and version:
        return version
    return "unknown"


def endpoint(environ: Mapping[str, str] | None = None) -> str:
    """Return the endpoint the bridge will publish once the server is ported."""
    env = os.environ if environ is None else environ
    configured = env.get("ASTRA_OPCUA_ENDPOINT", "").strip()
    if configured:
        return configured
    return DEFAULT_ENDPOINT


def tag_path(packet_name: str, field: str) -> str:
    """Return the OPC UA tag path for one field."""
    return f"Astra{packet_name}/{field}"
