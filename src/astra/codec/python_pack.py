"""Integer-shift packer for one Astra payload.

``AstraVarPacket.pas`` ``TBitStream.SaveBit`` ORs each bit into a buffer
that ``SavePacket`` has filled with zeros. Bit 0 of a value is the next
least-significant bit of the next byte, and multi-byte values continue
little-endian. Q types are the raw integer (``SaveValue`` does not scale).

Out-of-range integers keep the low bits (300 as ``u8`` is ``2c``). Null
packs as 0. ``overflow="clip"`` saturates a field to its type limits.
A checksum uses ``truncate_checksum`` and keeps its low bits. This payload
has no checksum.
"""

import math
import struct
from collections.abc import Sequence
from typing import Literal, assert_never

from astra.codec.errors import CodecError
from astra.codec.types import FLOAT_TYPE_IDS, SIGNED_TYPE_IDS, TYPE_WIDTH, FlatField

Value = bool | int | float | None
Overflow = Literal["clip", "wrap"]

# Largest finite IEEE-754 binary32 value. binary64 uses ``sys.float_info.max``.
_F32_MAX = float(struct.unpack("<f", b"\xff\xff\x7f\x7f")[0])
_F64_MAX = float(struct.unpack("<d", b"\xff\xff\xff\xff\xff\xff\xef\x7f")[0])


def pack_flat(
    layout: Sequence[FlatField],
    values: Sequence[Value],
    *,
    overflow: Overflow = "wrap",
) -> bytes:
    """Pack ``values`` in ``layout`` order into a zeroed payload.

    ``overflow="wrap"`` (the default) keeps the low bits the way Delphi
    ``SaveValue`` did. ``overflow="clip"`` saturates each field to its type.
    """
    mode = _check_overflow(overflow)
    if len(layout) != len(values):
        raise CodecError(f"layout has {len(layout)} scalars and {len(values)} values were given")
    bit_count = 0
    prepared: list[tuple[int, int]] = []
    for item, value in zip(layout, values, strict=True):
        _check_width(item)
        prepared.append((_bits_of(item, value, mode), item.bit_width))
        bit_count += item.bit_width
    return _pack_prepared(prepared, bit_count)


def unpack_flat(layout: Sequence[FlatField], payload: bytes) -> tuple[Value, ...]:
    """Unpack a payload whose length is exactly the padded layout size."""
    bit_count = 0
    for item in layout:
        _check_width(item)
        bit_count += item.bit_width
    size = (bit_count + 7) // 8
    if len(payload) != size:
        raise CodecError(f"payload is {len(payload)} bytes; layout packs to {size}")
    position = 0
    unpacked: list[Value] = []
    for item in layout:
        raw, position = _read_bits(payload, position, item.bit_width)
        unpacked.append(_value_of(item, raw))
    return tuple(unpacked)


def _check_width(item: FlatField) -> None:
    expected = TYPE_WIDTH.get(item.kind)
    if expected is None or item.bit_width != expected:
        raise CodecError(f"{item.name}: kind {item.kind} does not have width {item.bit_width}")


def pack_unsigned_bits(
    widths: Sequence[int],
    values: Sequence[int | None],
    *,
    overflow: Overflow = "wrap",
) -> bytes:
    """Pack unsigned integers of explicit bit widths.

    Used for minor-frame fields whose widths come from the database rather
    than from ``TVehicleDataTypes``. Null is 0. The default keeps the low
    bits. ``overflow="clip"`` saturates to ``[0, 2^width-1]``.
    """
    mode = _check_overflow(overflow)
    if len(widths) != len(values):
        raise CodecError(f"{len(widths)} widths and {len(values)} values were given")
    prepared: list[tuple[int, int]] = []
    bit_count = 0
    for index, (width, value) in enumerate(zip(widths, values, strict=True)):
        _require_width(width, index)
        prepared.append((_unsigned_bits(value, width, f"field {index}", mode), width))
        bit_count += width
    return _pack_prepared(prepared, bit_count)


def truncate_checksum(total: int, width: int) -> int:
    """Keep the low ``width`` bits of a checksum or accumulator.

    The sum is truncated to the field width. A Chapter 10 checksum uses this
    when that path is implemented. The live UDP payload has no checksum of
    its own.
    """
    if isinstance(total, bool) or not isinstance(total, int):
        raise CodecError(f"checksum total must be an int, got {total!r}")
    if isinstance(width, bool) or not isinstance(width, int) or width < 1:
        raise CodecError(f"checksum width must be an integer >= 1, got {width!r}")
    return total & ((1 << width) - 1)


def unpack_unsigned_bits(widths: Sequence[int], payload: bytes) -> tuple[int, ...]:
    """Unpack unsigned integers written by ``pack_unsigned_bits``."""
    bit_count = 0
    for index, width in enumerate(widths):
        _require_width(width, index)
        bit_count += width
    size = (bit_count + 7) // 8
    if len(payload) != size:
        raise CodecError(f"payload is {len(payload)} bytes; layout packs to {size}")
    position = 0
    unpacked: list[int] = []
    for width in widths:
        raw, position = _read_bits(payload, position, width)
        unpacked.append(raw)
    return tuple(unpacked)


def _require_width(width: int, index: int) -> None:
    if isinstance(width, bool) or not isinstance(width, int) or width < 1:
        raise CodecError(f"bit width {width!r} at index {index} must be an integer >= 1")


def _bits_of(item: FlatField, value: Value, overflow: Overflow) -> int:
    if item.kind in FLOAT_TYPE_IDS:
        return _float_to_bits(item, value, overflow)
    if item.kind == 1:
        return _bool_to_bits(item, value, overflow)
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise CodecError(f"{item.name}: expected an int, got {type(value).__name__}")
    if overflow == "wrap":
        return _low_bits(value, item.bit_width, item.name)
    if overflow == "clip":
        return _clip_int(value, item.bit_width, signed=item.kind in SIGNED_TYPE_IDS)
    assert_never(overflow)


def _value_of(item: FlatField, raw: int) -> Value:
    if item.kind in FLOAT_TYPE_IDS:
        size = item.bit_width // 8
        packed = raw.to_bytes(size, "little")
        fmt = "<f" if item.kind == 9 else "<d"
        decoded: float
        (decoded,) = struct.unpack(fmt, packed)
        return decoded
    if item.kind == 1:
        return raw == 1
    if item.kind in SIGNED_TYPE_IDS:
        sign = 1 << (item.bit_width - 1)
        if raw & sign:
            return raw - (1 << item.bit_width)
        return raw
    return raw


def _low_bits(value: int | None, width: int, name: str) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise CodecError(f"{name}: expected an int, got {type(value).__name__}")
    return value & ((1 << width) - 1)


def _unsigned_bits(value: int | None, width: int, name: str, overflow: Overflow) -> int:
    if overflow == "wrap":
        return _low_bits(value, width, name)
    if overflow == "clip":
        if value is None:
            return 0
        if isinstance(value, bool) or not isinstance(value, int):
            raise CodecError(f"{name}: expected an int, got {type(value).__name__}")
        return _clip_int(value, width, signed=False)
    assert_never(overflow)


def _clip_int(value: int, width: int, *, signed: bool) -> int:
    """Saturate ``value`` and return its low ``width`` bits."""
    if signed:
        limit = 1 << (width - 1)
        if value < -limit:
            value = -limit
        elif value > limit - 1:
            value = limit - 1
    else:
        maximum = (1 << width) - 1
        if value < 0:
            value = 0
        elif value > maximum:
            value = maximum
    return value & ((1 << width) - 1)


def _bool_to_bits(item: FlatField, value: Value, overflow: Overflow) -> int:
    if value is None or value is False:
        return 0
    if value is True:
        return 1
    if isinstance(value, int):
        if overflow == "wrap":
            return value & 1
        if overflow == "clip":
            return 0 if value == 0 else 1
        assert_never(overflow)
    raise CodecError(f"{item.name}: a bool field must be a bool, an int, or null")


def _float_to_bits(item: FlatField, value: Value, overflow: Overflow) -> int:
    if value is None:
        value = 0.0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CodecError(f"{item.name}: expected a float, got {type(value).__name__}")
    number = float(value)
    if overflow == "clip":
        number = _saturate_float(item.kind, number)
    elif overflow != "wrap":
        assert_never(overflow)
    fmt = "<f" if item.kind == 9 else "<d"
    try:
        raw = struct.pack(fmt, number)
    except OverflowError as exc:
        width = TYPE_WIDTH[item.kind]
        raise CodecError(f"{item.name}: {value} does not fit in {width} bits") from exc
    return int.from_bytes(raw, "little")


def _saturate_float(kind: int, value: float) -> float:
    """Clamp a finite float to the type's finite range.

    NaN and infinities are encodings the type can store, so they pass
    through. A finite value outside that range saturates to the extreme.
    """
    if math.isnan(value) or math.isinf(value):
        return value
    limit = _F32_MAX if kind == 9 else _F64_MAX
    if value > limit:
        return limit
    if value < -limit:
        return -limit
    return value


def _check_overflow(overflow: str) -> Overflow:
    if overflow == "clip":
        return "clip"
    if overflow == "wrap":
        return "wrap"
    raise CodecError(f"overflow must be 'clip' or 'wrap', got {overflow!r}")


def _pack_prepared(prepared: list[tuple[int, int]], bit_count: int) -> bytes:
    buffer = bytearray((bit_count + 7) // 8)
    position = 0
    for bits, width in prepared:
        position = _write_bits(buffer, position, bits, width)
    return bytes(buffer)


def _write_bits(buffer: bytearray, position: int, value: int, width: int) -> int:
    """OR ``width`` bits into ``buffer``. Bit 0 of ``value`` is written first."""
    remaining = width
    bits = value
    while remaining:
        byte_index = position >> 3
        bit_in_byte = position & 7
        take = min(8 - bit_in_byte, remaining)
        mask = (1 << take) - 1
        buffer[byte_index] |= (bits & mask) << bit_in_byte
        bits >>= take
        remaining -= take
        position += take
    return position


def _read_bits(payload: bytes, position: int, width: int) -> tuple[int, int]:
    value = 0
    shift = 0
    remaining = width
    while remaining:
        byte_index = position >> 3
        bit_in_byte = position & 7
        take = min(8 - bit_in_byte, remaining)
        mask = (1 << take) - 1
        chunk = (payload[byte_index] >> bit_in_byte) & mask
        value |= chunk << shift
        shift += take
        remaining -= take
        position += take
    return value, position
