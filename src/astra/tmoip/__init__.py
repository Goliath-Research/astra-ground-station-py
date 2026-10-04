"""Telemetry-over-IP minor frames.

Listens on ``ASTRA_BRIDGE_PORT + stage`` for stages ``1 .. ASTRA_STAGE_COUNT``
(defaults: port 2357 and two stages, so 2358 and 2359). Reassembled
``id || body`` datagrams go to ``127.0.0.1`` on ``ASTRA_BRIDGE_PORT``. The
Delphi decoder hard-coded that host and port and always built stages 1 and 2.

An IRIG106 minor frame is a normal Astra packet. The encoder sends it with
no id prefix. There is no checksum on the live frame.
"""

from astra.settings import bridge_port, stage_count, stage_port, stage_ports
from astra.tmoip.decoder import (
    BRIDGE_HOST,
    ForwardedDatagram,
    LoggedMinorFrame,
    StageDecoder,
    reassemble,
)
from astra.tmoip.encoder import EncodedMinorFrame, MinorFrameEncoder, StreamPacket
from astra.tmoip.irig import irig106_fields
from astra.tmoip.rate import frame_due, minor_frame_packet_id

__all__ = [
    "BRIDGE_HOST",
    "EncodedMinorFrame",
    "ForwardedDatagram",
    "LoggedMinorFrame",
    "MinorFrameEncoder",
    "StageDecoder",
    "StreamPacket",
    "bridge_port",
    "frame_due",
    "irig106_fields",
    "minor_frame_packet_id",
    "reassemble",
    "stage_count",
    "stage_port",
    "stage_ports",
]
