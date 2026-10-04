"""IRIG106 minor-frame layout.

The minor frame is an ordinary Astra packet. Its ``sf_id``, ``row_id``, and
``packet_stream`` types, widths, and array length come from the database.
The vectors use the fixture ``sf_id: u8``, ``row_id: i32``,
``packet_stream: u8[4]``.
"""

from collections.abc import Sequence

from astra.codec.errors import CodecError
from astra.codec.types import SIGNED_TYPE_IDS, TYPE_WIDTH, Field


def irig106_fields(
    *,
    sf_id_type: int = 2,
    row_id_type: int = 8,
    stream_type: int = 2,
    stream_qty: int = 4,
) -> tuple[Field, Field, Field]:
    """Return the IRIG106 fields. Defaults are the codec-vector fixture."""
    return (
        Field("sf_id", sf_id_type),
        Field("row_id", row_id_type),
        Field("packet_stream", stream_type, qty=stream_qty),
    )


def require_irig_fields(fields: Sequence[Field]) -> tuple[Field, Field, Field]:
    """Return ``(sf_id, row_id, packet_stream)`` or raise."""
    if len(fields) != 3 or [field.name for field in fields] != [
        "sf_id",
        "row_id",
        "packet_stream",
    ]:
        raise CodecError("IRIG106 fields must be sf_id, row_id, packet_stream")
    sf_id, row_id, stream = fields
    for field in (sf_id, row_id):
        if field.qty != 1 or field.fields or field.override:
            raise CodecError(f"{field.name} must be one scalar with no override")
    if stream.fields or stream.override:
        raise CodecError("packet_stream must be a scalar array with no override")
    if stream_nbytes(stream) < 1:
        raise CodecError("packet_stream must occupy at least one byte")
    return sf_id, row_id, stream


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
