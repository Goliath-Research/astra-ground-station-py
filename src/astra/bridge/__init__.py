"""UDP bridge.

One process replaces ``AstraBridgeServer`` and ``AstraBridgeServerDesktop``.
It will poll ``config.tests``, bind ``ASTRA_BRIDGE_PORT`` (default 2357),
write ``.DAT`` files, and publish OPC UA tags through :mod:`astra.opcua`.
None of that runs yet.
"""

from astra.opcua import endpoint, tag_path
from astra.settings import bridge_port

__all__ = ["bridge_port", "endpoint", "tag_path"]
