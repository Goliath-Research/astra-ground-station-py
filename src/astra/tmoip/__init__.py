"""Telemetry-over-IP minor-frame reassembly.

Listens on ``ASTRA_BRIDGE_PORT + stage`` for stages ``1 .. ASTRA_STAGE_COUNT``
(defaults: port 2357 and two stages, so 2358 and 2359) and forwards
reassembled datagrams to the bridge on ``ASTRA_BRIDGE_PORT``. The Delphi
decoder hard-coded ``127.0.0.1:2357`` and always constructed stages 1 and 2.
"""

from astra.settings import bridge_port, stage_count, stage_port, stage_ports

__all__ = [
    "bridge_port",
    "reassemble",
    "stage_count",
    "stage_port",
    "stage_ports",
]


def reassemble(datagram: bytes) -> bytes:
    """Pull Astra packets out of one minor frame.

    Raises:
        NotImplementedError: always, until phase 4.
    """
    del datagram
    raise NotImplementedError("TMoIP reassembly is not ported")
