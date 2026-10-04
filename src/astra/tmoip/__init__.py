"""Telemetry-over-IP minor-frame reassembly.

Listens on ``ASTRA_BRIDGE_PORT + stage`` for stages ``1 .. ASTRA_STAGE_COUNT``
(defaults: port 2357 and two stages, so 2358 and 2359) and forwards
reassembled datagrams to the bridge on ``ASTRA_BRIDGE_PORT``. The Delphi
decoder hard-coded ``127.0.0.1:2357`` and always constructed stages 1 and 2.
"""

from astra.settings import bridge_port, stage_count, stage_port, stage_ports

__all__ = [
    "bridge_port",
    "frame_due",
    "minor_frame_packet_id",
    "reassemble",
    "stage_count",
    "stage_port",
    "stage_ports",
]


def minor_frame_packet_id(stage: int) -> int:
    """Return the packet id of the logged IRIG minor frame for ``stage``.

    ``TAstraDecoder`` uses ``100 * (stage - 1) + 106``. How many stages exist
    is ``ASTRA_STAGE_COUNT``; this formula does not assume two.
    """
    if isinstance(stage, bool) or not isinstance(stage, int) or stage < 1:
        raise ValueError(f"stage must be an integer >= 1, got {stage!r}")
    return 100 * (stage - 1) + 106


def frame_due(sequence: int, packet_rate: int, irig_rate: int) -> bool:
    """Return whether a packet of ``packet_rate`` is due at ``sequence``.

    ``AstraTMEncoder`` inserts a packet when
    ``Sequence * packetRate mod irigRate = 0``. ``packet_stream`` is then
    zero-filled. The widths of ``sf_id``, ``row_id``, and ``packet_stream``
    are not in the readable notes, so this does not build the frame bytes.
    """
    _require_non_negative("sequence", sequence)
    _require_non_negative("packet_rate", packet_rate)
    if isinstance(irig_rate, bool) or not isinstance(irig_rate, int) or irig_rate < 1:
        raise ValueError(f"irig_rate must be an integer >= 1, got {irig_rate!r}")
    return (sequence * packet_rate) % irig_rate == 0


def _require_non_negative(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be an integer >= 0, got {value!r}")


def reassemble(datagram: bytes) -> bytes:
    """Pull Astra packets out of one minor frame.

    Raises:
        NotImplementedError: always, until phase 4.
    """
    del datagram
    raise NotImplementedError("TMoIP reassembly is not ported")
