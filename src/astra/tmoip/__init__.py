"""Telemetry-over-IP minor frames.

Listens on ``ASTRA_BRIDGE_PORT + stage`` for stages ``1 .. ASTRA_STAGE_COUNT``
(defaults: port 2357 and two stages, so 2358 and 2359). Reassembled
``id || body`` datagrams go to ``127.0.0.1`` on ``ASTRA_BRIDGE_PORT``. The
Delphi decoder hard-coded that host and port and always built stages 1 and 2.

An IRIG106 minor frame is a normal Astra packet. The default layout is the
349-byte database packet. The encoder sends it with no id prefix and reads
``sf_id``, ``row_id``, and ``packet_stream`` by name. There is no checksum
on the live frame. The decoder logs that datagram as packet 106 or 206;
the database packet ids are 1061 and 1062.
"""

from astra.settings import bridge_port, stage_count, stage_port, stage_ports
from astra.tmoip.decoder import (
    BRIDGE_HOST,
    MAX_SF_ID,
    ForwardedDatagram,
    LoggedMinorFrame,
    StageDecoder,
    reassemble,
)
from astra.tmoip.encoder import EncodedMinorFrame, MinorFrameEncoder, StreamPacket
from astra.tmoip.irig import (
    CALCULATED_INPUT_PACKETS,
    IRIG106_PACKET_IDS,
    STORED_INPUT_PACKETS,
    irig106_fields,
    spec_fixture_fields,
)
from astra.tmoip.rate import (
    CONFIG_FREQUENCIES_HZ,
    DEFAULT_ENCODER_RATE_HZ,
    frame_due,
    minor_frame_packet_id,
)

__all__ = [
    "BRIDGE_HOST",
    "CALCULATED_INPUT_PACKETS",
    "CONFIG_FREQUENCIES_HZ",
    "DEFAULT_ENCODER_RATE_HZ",
    "EncodedMinorFrame",
    "ForwardedDatagram",
    "IRIG106_PACKET_IDS",
    "LoggedMinorFrame",
    "MAX_SF_ID",
    "MinorFrameEncoder",
    "STORED_INPUT_PACKETS",
    "StageDecoder",
    "StreamPacket",
    "bridge_port",
    "frame_due",
    "irig106_fields",
    "minor_frame_packet_id",
    "reassemble",
    "spec_fixture_fields",
    "stage_count",
    "stage_port",
    "stage_ports",
]
