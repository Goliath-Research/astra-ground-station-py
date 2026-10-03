"""OPC UA bridge.

Replaces OPC DA and NI shared variables. LabVIEW will subscribe to tags
published by this process. The server is not started yet, and the tag
dictionary is not defined yet.
"""

import os
from collections.abc import Mapping

import asyncua

DEFAULT_ENDPOINT = "opc.tcp://0.0.0.0:4840/astra/"


def opcua_library_version() -> str:
    """Return the installed asyncua version, proving the dependency imports."""
    version = asyncua.__version__
    if isinstance(version, str) and version:
        return version
    return "unknown"


def opcua_endpoint(environ: Mapping[str, str] | None = None) -> str:
    """Return the endpoint the bridge will publish once the server is ported."""
    env = os.environ if environ is None else environ
    endpoint = env.get("ASTRA_OPCUA_ENDPOINT", "").strip()
    if endpoint:
        return endpoint
    return DEFAULT_ENDPOINT
