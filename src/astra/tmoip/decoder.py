"""TMoIP minor-frame decoder from ``AstraTMoIP/AstraDecoder.pas``.

``IdUDPServerUDPRead`` (275-279) drops a frame when ``row_id`` is below the
last accepted row, when ``row_id`` is greater than ``estimated_row_id + 10``,
or when ``sf_id > 16``. The raw datagram is logged under
``FPacketID = 100 * (stage - 1) + 106`` (106 on stage 1, 206 on stage 2).
Those log ids are not the database packet ids 1061 and 1062.

``PushStream`` (304-347) starts a new major frame when ``row_id`` is 0 or
greater than the last accepted row. A minor frame is consumed only when
``sf_id`` is one past the last accepted subframe. After a gap, the rest of
that row is ignored.

``StartNewPacket`` (378-408) reads a signed int32 id and accepts it only
when ``id > 0`` and the id is a known input packet. The pending size is
``EncSize + 4``. ``PushBufferToPacket`` (349-376) fills those bytes across
minor frames. ``SendAndClearPacket`` (410-414) UDP-sends ``id || body``
unchanged to ``127.0.0.1`` on the configured bridge port.
"""

import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from astra.codec import pack, unpack
from astra.codec.errors import CodecError
from astra.codec.types import Field
from astra.settings import bridge_port
from astra.tmoip.irig import IrigRoles, irig106_fields, require_irig_fields
from astra.tmoip.rate import minor_frame_packet_id

_INT32 = struct.Struct("<i")
BRIDGE_HOST = "127.0.0.1"
MAX_SF_ID = 16
ROW_JUMP = 10


@dataclass(frozen=True, slots=True)
class LoggedMinorFrame:
    """A raw minor-frame datagram logged under the stage packet id."""

    packet_id: int
    datagram: bytes


@dataclass(frozen=True, slots=True)
class ForwardedDatagram:
    """Bytes ``SendAndClearPacket`` would UDP-send to the bridge."""

    host: str
    port: int
    payload: bytes


@dataclass
class StageDecoder:
    """One stage's minor-frame state machine.

    ``known`` maps an input packet id to its ``EncSize`` (payload bytes, not
    counting the 4-byte id). An id that is not accepted consumes those four
    bytes and does not collect a body, so a later known id can still start.
    """

    stage: int
    known: Mapping[int, int]
    estimated_row_id: int = 0
    fields: Sequence[Field] | None = None
    environ: Mapping[str, str] | None = None
    logged: list[LoggedMinorFrame] = field(default_factory=list)
    forwarded: list[ForwardedDatagram] = field(default_factory=list)
    last_row_id: int = 0
    last_sf_id: int = 0
    _skip_row: bool = False
    _buffer: bytearray = field(default_factory=bytearray)
    _target: int = 0
    _fields: tuple[Field, ...] = field(init=False)
    _roles: IrigRoles = field(init=False)
    _stream: Field = field(init=False)
    log_packet_id: int = field(init=False)
    _bridge_port: int = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.stage, bool) or not isinstance(self.stage, int) or self.stage < 1:
            raise ValueError(f"stage must be an integer >= 1, got {self.stage!r}")
        if isinstance(self.estimated_row_id, bool) or not isinstance(self.estimated_row_id, int):
            raise ValueError(f"estimated_row_id must be an int, got {self.estimated_row_id!r}")
        for packet_id, enc_size in self.known.items():
            if isinstance(packet_id, bool) or not isinstance(packet_id, int):
                raise CodecError(f"known packet id {packet_id!r} must be an int")
            if isinstance(enc_size, bool) or not isinstance(enc_size, int) or enc_size < 0:
                raise CodecError(f"enc size for packet {packet_id} must be an integer >= 0")
        chosen = irig106_fields() if self.fields is None else tuple(self.fields)
        self._fields = chosen
        self._roles = require_irig_fields(chosen)
        self._stream = self._roles.packet_stream
        self.log_packet_id = minor_frame_packet_id(self.stage)
        self._bridge_port = bridge_port(self.environ)

    def udp_read(self, datagram: bytes) -> None:
        """Handle one minor-frame UDP payload (no id prefix)."""
        self.logged.append(LoggedMinorFrame(self.log_packet_id, bytes(datagram)))
        unpacked = unpack(self._fields, datagram)
        sf_id = _as_int("sf_id", unpacked[self._roles.sf_index])
        row_id = _as_int("row_id", unpacked[self._roles.row_index])
        too_early = row_id < self.last_row_id
        too_late = row_id > self.estimated_row_id + ROW_JUMP
        if too_early or too_late or sf_id > MAX_SF_ID:
            return
        start = self._roles.stream_index
        stream_values = unpacked[start : start + self._stream.qty]
        plain = Field(self._stream.name, self._stream.type_id, qty=self._stream.qty)
        self.push_stream(sf_id, row_id, pack((plain,), stream_values))

    def push_stream(self, sf_id: int, row_id: int, packet_stream: bytes) -> None:
        """Accept a subframe or ignore the rest of its row."""
        if row_id == 0 or row_id > self.last_row_id:
            self.last_row_id = row_id
            self.last_sf_id = 0
            self._skip_row = False
        if self._skip_row:
            return
        if sf_id != self.last_sf_id + 1:
            self._skip_row = True
            return
        self.last_sf_id = sf_id
        self.push_buffer_to_packet(packet_stream)

    def push_buffer_to_packet(self, data: bytes) -> None:
        """Fill the current input packet, across minor frames if needed."""
        self._buffer.extend(data)
        self._drain()

    def _drain(self) -> None:
        while True:
            if self._target == 0:
                if len(self._buffer) < _INT32.size:
                    return
                (packet_id,) = _INT32.unpack_from(self._buffer, 0)
                if packet_id <= 0 or packet_id not in self.known:
                    del self._buffer[: _INT32.size]
                    continue
                self._target = self.known[packet_id] + _INT32.size
            if len(self._buffer) < self._target:
                return
            payload = bytes(self._buffer[: self._target])
            del self._buffer[: self._target]
            self._target = 0
            self.forwarded.append(ForwardedDatagram(BRIDGE_HOST, self._bridge_port, payload))


def reassemble(datagram: bytes, decoder: StageDecoder) -> None:
    """Feed one minor frame into ``decoder``."""
    decoder.udp_read(datagram)


def _as_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CodecError(f"{name} must be an int, got {type(value).__name__}")
    return value
