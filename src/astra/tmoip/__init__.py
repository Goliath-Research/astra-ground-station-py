"""Telemetry-over-IP minor-frame reassembly.

Listens on ``ASTRA_BRIDGE_PORT + stage`` for stages ``1 .. ASTRA_STAGE_COUNT``
(defaults: port 2357 and two stages, so 2358 and 2359) and forwards
reassembled datagrams to the bridge on ``ASTRA_BRIDGE_PORT``. The Delphi
decoder hard-coded ``127.0.0.1:2357`` and always constructed stages 1 and 2.

Building one minor frame is ported. Pulling variable packets back out of
``packet_stream`` (``PushBufferToPacket``) is not: that needs the packet
size table. The live frame has no checksum.
"""

import struct
from dataclasses import dataclass

from astra.codec.errors import CodecError
from astra.codec.python_pack import pack_unsigned_bits, unpack_unsigned_bits
from astra.settings import bridge_port, stage_count, stage_port, stage_ports

__all__ = [
    "MinorFrameLayout",
    "bridge_port",
    "build_minor_frame",
    "frame_due",
    "minor_frame_packet_id",
    "parse_minor_frame",
    "reassemble",
    "stage_count",
    "stage_port",
    "stage_ports",
]

_INT32 = struct.Struct("<i")


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

    ``AstraTMEncoder`` evaluates this before ``Sequence`` increments:
    ``(Sequence = 0) or (Sequence * packetRate mod irigRate = 0)``.
    """
    _require_non_negative("sequence", sequence)
    _require_non_negative("packet_rate", packet_rate)
    if isinstance(irig_rate, bool) or not isinstance(irig_rate, int) or irig_rate < 1:
        raise ValueError(f"irig_rate must be an integer >= 1, got {irig_rate!r}")
    return sequence == 0 or (sequence * packet_rate) % irig_rate == 0


@dataclass(frozen=True, slots=True)
class MinorFrameLayout:
    """Widths of ``sf_id``, ``row_id``, and ``packet_stream``.

    Those widths come from the database, not from a fixed type id. The
    vectors that would pin one fixture layout were not loaded.
    ``packet_stream_bytes`` is the stream width in bytes and must be at
    least 4, the signed int32 packet id the encoder writes at the front.
    """

    sf_id_bits: int
    row_id_bits: int
    packet_stream_bytes: int

    def __post_init__(self) -> None:
        _require_positive("sf_id_bits", self.sf_id_bits)
        _require_positive("row_id_bits", self.row_id_bits)
        if (
            isinstance(self.packet_stream_bytes, bool)
            or not isinstance(self.packet_stream_bytes, int)
            or self.packet_stream_bytes < 4
        ):
            raise ValueError(
                f"packet_stream_bytes must be an integer >= 4, got {self.packet_stream_bytes!r}"
            )


def build_minor_frame(
    sf_id: int,
    row_id: int,
    packet_id: int,
    layout: MinorFrameLayout,
) -> bytes:
    """Pack one minor frame and leave the stream payload zero.

    ``sf_id`` and ``row_id`` are unsigned fields of ``layout``'s bit widths,
    LSB first, with no byte pad between them. ``packet_stream`` follows
    immediately. Its first four bytes are ``packet_id`` as a signed int32
    little-endian, and every following byte is zero. There is no checksum.
    """
    stream = _packet_stream(packet_id, layout.packet_stream_bytes)
    widths = [layout.sf_id_bits, layout.row_id_bits, *(8 for _byte in stream)]
    values: list[int | None] = [sf_id, row_id, *stream]
    return pack_unsigned_bits(widths, values)


def parse_minor_frame(frame: bytes, layout: MinorFrameLayout) -> tuple[int, int, int, bytes]:
    """Return ``(sf_id, row_id, packet_id, packet_stream)``."""
    stream_widths = [8 for _byte in range(layout.packet_stream_bytes)]
    widths = [layout.sf_id_bits, layout.row_id_bits, *stream_widths]
    sf_id, row_id, *stream_bytes = unpack_unsigned_bits(widths, frame)
    stream = bytes(stream_bytes)
    packet_id: int
    (packet_id,) = _INT32.unpack_from(stream, 0)
    return sf_id, row_id, packet_id, stream


def _packet_stream(packet_id: int, size: int) -> bytes:
    if isinstance(packet_id, bool) or not isinstance(packet_id, int):
        raise CodecError("packet id must be an int")
    if packet_id < -0x80000000 or packet_id > 0x7FFFFFFF:
        raise CodecError(f"packet id {packet_id} does not fit in a signed 32-bit integer")
    return _INT32.pack(packet_id) + bytes(size - 4)


def _require_non_negative(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be an integer >= 0, got {value!r}")


def _require_positive(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be an integer >= 1, got {value!r}")


def reassemble(datagram: bytes) -> bytes:
    """Pull Astra packets out of one minor frame.

    Raises:
        NotImplementedError: always, until phase 4.
    """
    del datagram
    raise NotImplementedError("TMoIP reassembly is not ported")
