"""UDP bridge.

One process replaces ``AstraBridgeServer`` and ``AstraBridgeServerDesktop``.
It will poll ``config.tests``, bind the UDP port from ``config.servers``,
write ``.DAT`` files, and publish OPC UA tags through :mod:`astra.opcua`.
None of that runs yet.
"""

from astra.opcua import endpoint, tag_path

__all__ = ["endpoint", "tag_path"]
