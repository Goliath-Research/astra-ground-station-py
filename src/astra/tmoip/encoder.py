"""Minor-frame encoder from ``AstraTMEncoder/_AstraTMEncoder.pas``.

``BuildPacketStream`` (168-210) appends, for each packet that passes the
rate rule, a signed int32 little-endian packet id and then ``EncSize`` zero
bytes. Only the id is copied; the payload bytes stay zero. If ``PacketStream``
still has bytes, the routine only increments ``SubFrameID`` and returns.
Otherwise it builds a new stream, increments ``Sequence``, and sets
``SubFrameID`` to 1.

``Timer1Timer`` (212-276) copies ``min(len(stream), len(packet_stream))``
bytes into the IRIG106 ``packet_stream`` field, zero-fills the rest, and
deletes that prefix (236-250). The packed IRIG106 packet is sent with no
id prefix to the stage listen port, ``bridge port + stage`` (294-296).
"""

import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from astra.codec import pack
from astra.codec.errors import CodecError
from astra.codec.python_pack import Value
from astra.codec.types import Field
from astra.settings import stage_port
from astra.tmoip.irig import (
    irig106_fields,
    require_irig_fields,
    stream_nbytes,
    values_from_stream_bytes,
)
from astra.tmoip.rate import frame_due

_INT32 = struct.Struct("<i")


@dataclass(frozen=True, slots=True)
class StreamPacket:
    """One packet the encoder may place on the minor-frame stream."""

    packet_id: int
    packet_rate: int
    enc_size: int

    def __post_init__(self) -> None:
        if isinstance(self.packet_id, bool) or not isinstance(self.packet_id, int):
            raise CodecError("packet id must be an int")
        if self.packet_id < -0x80000000 or self.packet_id > 0x7FFFFFFF:
            raise CodecError(f"packet id {self.packet_id} does not fit in a signed 32-bit integer")
        if isinstance(self.packet_rate, bool) or not isinstance(self.packet_rate, int):
            raise CodecError(f"packet_rate must be an integer >= 0, got {self.packet_rate!r}")
        if self.packet_rate < 0:
            raise CodecError(f"packet_rate must be an integer >= 0, got {self.packet_rate!r}")
        if isinstance(self.enc_size, bool) or not isinstance(self.enc_size, int):
            raise CodecError(f"enc_size must be an integer >= 0, got {self.enc_size!r}")
        if self.enc_size < 0:
            raise CodecError(f"enc_size must be an integer >= 0, got {self.enc_size!r}")


@dataclass(frozen=True, slots=True)
class EncodedMinorFrame:
    """One IRIG106 payload and the UDP port it is sent to."""

    payload: bytes
    port: int
    sf_id: int
    row_id: int


class MinorFrameEncoder:
    """Build IRIG106 payloads the way ``Timer1Timer`` does.

    ``row_id`` stays at the value given here. The two codec vectors keep it
    at 1 across a continued stream, and the Delphi notes do not say when the
    encoder advances the row.
    """

    def __init__(
        self,
        packets: Sequence[StreamPacket],
        *,
        irig_rate: int,
        row_id: int = 1,
        stage: int = 1,
        fields: Sequence[Field] | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._packets = tuple(packets)
        self._irig_rate = irig_rate
        self._row_id = row_id
        self._stage = stage
        self._environ = environ
        self._fields = irig106_fields() if fields is None else tuple(fields)
        _sf, _row, stream = require_irig_fields(self._fields)
        self._stream_field = stream
        self._stream_size = stream_nbytes(stream)
        self.sequence = 0
        self.subframe_id = 0
        self._stream = bytearray()
        if isinstance(row_id, bool) or not isinstance(row_id, int):
            raise CodecError(f"row_id must be an int, got {row_id!r}")

    def build_packet_stream(self) -> None:
        """Append due packets, or only advance ``SubFrameID``."""
        if self._stream:
            self.subframe_id += 1
            return
        built = bytearray()
        for packet in self._packets:
            if frame_due(self.sequence, packet.packet_rate, self._irig_rate):
                built += _INT32.pack(packet.packet_id)
                built += bytes(packet.enc_size)
        self._stream = built
        self.sequence += 1
        self.subframe_id = 1

    def tick(self) -> EncodedMinorFrame:
        """Copy the next prefix into an IRIG106 packet and return it.

        The payload has no leading packet id. ``port`` is the stage listen
        port from settings (default 2358 for stage 1).
        """
        self.build_packet_stream()
        take = min(len(self._stream), self._stream_size)
        copied = bytes(self._stream[:take])
        del self._stream[:take]
        padded = copied + bytes(self._stream_size - len(copied))
        stream_values = values_from_stream_bytes(self._stream_field, padded)
        values: list[Value] = [self.subframe_id, self._row_id, *stream_values]
        payload = pack(self._fields, values)
        return EncodedMinorFrame(
            payload,
            stage_port(self._stage, self._environ),
            self.subframe_id,
            self._row_id,
        )
