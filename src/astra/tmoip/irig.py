"""IRIG106 minor-frame layout from the migrated config database.

Stage 1 (VarType 421, packet 1061, node 6563) and Stage 2 (VarType 453,
packet 1062, node 6596) flatten to the same 349-byte packet. The codec
reads ``sf_id``, ``row_id``, and ``packet_stream`` by name. The other
fields pass through: the encoder zeroes them, and the decoder ignores
them except to reach the stream.

The transcribed spec vectors still use a smaller fixture
(``spec_fixture_fields``): ``sf_id`` u8, ``row_id`` i32, ``packet_stream``
u8[4]. That fixture is not this default.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from astra.codec.errors import CodecError
from astra.codec.types import SIGNED_TYPE_IDS, TYPE_WIDTH, Field, FlatField, flatten

# Stage-1 record ids. Stage 2 uses 454 / 455 / 456 and the same wire layout.
_FAP_TYPE_ID = 422
_FSS_TYPE_ID = 423
_ITS_TYPE_ID = 424

_FSS_NAMES = (
    "Reserved1",
    "Reserved2",
    "Reserved3",
    "MFL",
    "MFC",
    "MFS",
    "FSP",
    "Flywheel",
    "Idle",
    "Lock",
    "Check",
    "Search",
)

PACKET_STREAM_BYTES = 200
IRIG106_ENC_BYTES = 349
IRIG106_BITS = 2792
# config.packets.id. The decoder's log ids 106 and 206 are a different namespace.
IRIG106_PACKET_IDS = {1: 1061, 2: 1062}

# spGetInpPacketSizes: IconID 7, non-NULL EncSize, no stage filter, no ORDER BY.
# This is the order that query returned on the migrated data, not a sort.
STORED_INPUT_PACKETS: tuple[tuple[int, str, int], ...] = (
    (2, "R2L", 753),
    (6, "PSTR2L", 51),
    (107, "PSTR2LD", 51),
    (1060, "TMstats1", 48),
    (1061, "IRIG106", 349),
    (1062, "IRIG106", 349),
    (1063, "TMstats2", 48),
)
# Stored EncSize is NULL until spCalcVarTypeSizes. EngineR2L is the only R2L
# packet with override bits (14); its recalculated size is 132 bytes.
CALCULATED_INPUT_PACKETS: tuple[tuple[int, str, int], ...] = (
    (11, "EngineR2L", 132),
    (102, "R2L", 753),
)


@dataclass(frozen=True, slots=True)
class IrigRoles:
    """Where the three named fields sit in the flattened scalar list."""

    sf_id: Field
    row_id: Field
    packet_stream: Field
    sf_index: int
    row_index: int
    stream_index: int


def irig106_fields() -> tuple[Field, ...]:
    """Return the database IRIG106 packet, in ``Seq`` order.

    Multi-bit FAP counters are arrays of 1-bit bools. ``row_id`` is u32.
    ``packet_stream`` is 200 bytes. Nothing in this tree has Override.
    """
    its = Field(
        "IRIG_time_status",
        _ITS_TYPE_ID,
        seq=5,
        fields=(
            Field("IRIG_present", 1, seq=1),
            Field("Reserved", 1, qty=7, seq=2),
        ),
    )
    fss = Field(
        "frame_sync_status",
        _FSS_TYPE_ID,
        seq=6,
        fields=tuple(Field(name, 1, seq=index) for index, name in enumerate(_FSS_NAMES, start=1)),
    )
    fap = Field(
        "fap",
        _FAP_TYPE_ID,
        seq=1,
        fields=(
            Field("type", 2, seq=1),
            Field("seq_counter", 1, qty=13, seq=2),
            Field("bytes_in_packet", 1, qty=11, seq=3),
            Field("zeroes12", 1, qty=12, seq=4),
            its,
            fss,
            Field("milliseconds_in_the_day", 5, seq=7),
            Field("Subframe_id", 1, qty=10, seq=8),
            Field("words_per_minor_frame", 4, seq=9),
            Field("bits_per_word", 1, qty=6, seq=10),
            Field("bitrate", 5, seq=11),
        ),
    )
    return (
        fap,
        Field("fsp", 5, seq=2),
        Field("sf_id", 2, seq=3),
        Field("row_id", 5, seq=4),
        Field("range_variables", 2, qty=120, seq=5),
        Field("packet_stream", 2, qty=PACKET_STREAM_BYTES, seq=6),
    )


def spec_fixture_fields(*, stream_qty: int = 4) -> tuple[Field, Field, Field]:
    """Return the transcribed spec's small minor-frame fixture.

    ``docs/CODEC_SPEC.md`` packed its vectors as ``sf_id`` u8, ``row_id``
    i32, ``packet_stream`` u8[4]. The database layout replaced that as the
    default. Tests of the subframe state machine still pass this explicitly.
    """
    return (
        Field("sf_id", 2),
        Field("row_id", 8),
        Field("packet_stream", 2, qty=stream_qty),
    )


def require_irig_fields(fields: Sequence[Field]) -> IrigRoles:
    """Find ``sf_id``, ``row_id``, and ``packet_stream`` by name.

    Other fields are allowed and pass through. The three named fields are
    scalars with no override. ``packet_stream`` is a byte array.
    """
    found: dict[str, Field] = {}
    for field in fields:
        if field.name not in ("sf_id", "row_id", "packet_stream"):
            continue
        if field.name in found:
            raise CodecError(f"IRIG106 has more than one {field.name}")
        found[field.name] = field
    missing = [name for name in ("sf_id", "row_id", "packet_stream") if name not in found]
    if missing:
        raise CodecError("IRIG106 must include sf_id, row_id, and packet_stream")
    sf_id = found["sf_id"]
    row_id = found["row_id"]
    stream = found["packet_stream"]
    for field in (sf_id, row_id):
        if field.qty != 1 or field.fields or field.override:
            raise CodecError(f"{field.name} must be one scalar with no override")
    if stream.fields or stream.override:
        raise CodecError("packet_stream must be a scalar array with no override")
    if stream_nbytes(stream) < 1:
        raise CodecError("packet_stream must occupy at least one byte")
    layout = flatten(fields)
    return IrigRoles(
        sf_id,
        row_id,
        stream,
        _scalar_index(layout, sf_id),
        _scalar_index(layout, row_id),
        _scalar_index(layout, stream),
    )


def stream_nbytes(field: Field) -> int:
    """Return how many bytes ``packet_stream`` holds."""
    width = TYPE_WIDTH.get(field.type_id)
    if width is None or width % 8 != 0:
        raise CodecError(f"{field.name} type {field.type_id} is not a whole number of bytes")
    return field.qty * (width // 8)


def values_from_stream_bytes(field: Field, data: bytes) -> list[int]:
    """Split a byte buffer into the integers ``packet_stream`` stores."""
    step = TYPE_WIDTH[field.type_id] // 8
    if len(data) != field.qty * step:
        raise CodecError("packet_stream byte length does not match the field")
    signed = field.type_id in SIGNED_TYPE_IDS
    return [
        int.from_bytes(data[index * step : (index + 1) * step], "little", signed=signed)
        for index in range(field.qty)
    ]


def _scalar_index(layout: Sequence[FlatField], field: Field) -> int:
    target = field.name if field.qty == 1 else f"{field.name}_0"
    for index, item in enumerate(layout):
        if item.role == "value" and item.name == target:
            return index
    raise CodecError(f"{field.name} is not in the flattened IRIG106 layout")
