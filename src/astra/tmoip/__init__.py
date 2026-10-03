"""Telemetry-over-IP minor-frame reassembly.

``AstraTMoIP`` listens on UDP ``2357 + stage`` (stage 1 is 2358, stage 2 is
2359) and forwards reassembled datagrams to the bridge. The bridge address
is configuration; the Delphi code hard-codes ``127.0.0.1:2357``.
"""

BRIDGE_PORT_ASSUMED = 2357


def stage_port(stage: int) -> int:
    """Return the UDP port for one stage decoder."""
    return BRIDGE_PORT_ASSUMED + stage


def reassemble(datagram: bytes) -> bytes:
    """Pull Astra packets out of one minor frame.

    Raises:
        NotImplementedError: always, until phase 4.
    """
    del datagram
    raise NotImplementedError("TMoIP reassembly is not ported")
