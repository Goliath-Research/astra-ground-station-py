"""LSB-first unsigned bit packer for the Mojo toolchain smoke test.

Python ``astra.codec`` is still the packer the service calls. This module is
the small kernel CI compiles with Modular's published Mojo image. The default
saturates each unsigned field to its width, the same rule as
``pack(..., overflow="clip")``. ``overflow="wrap"`` keeps the low bits and is
how the transcribed vector ``u8_out_of_range_wraps`` (300 as ``u8`` is ``2c``)
stays verifiable.

The other byte checks are the in-range vectors ``u8``, ``u12``, and
``u12_after_bool`` from ``tests/data/codec_vectors.json``.
"""

from std.collections import Array

comptime PACK_BYTES = 8
comptime PACK_BITS = PACK_BYTES * 8


def clip_unsigned(value: Int, width: Int) -> Int:
    """Clamp ``value`` to ``[0, 2**width - 1]``."""
    var limit = (1 << width) - 1
    if value < 0:
        return 0
    if value > limit:
        return limit
    return value


def low_bits(value: Int, width: Int) -> Int:
    """Keep the low ``width`` bits. This is the legacy wrap mode."""
    return value & ((1 << width) - 1)


def clip_bool(value: Int) -> Int:
    """Clamp a bool field: zero stays zero, every other integer becomes one."""
    if value == 0:
        return 0
    return 1


def bool_bit(value: Int) -> Int:
    """Legacy bool wrap: keep the low bit. Two becomes zero; three becomes one."""
    return value & 1


def _field_bits(value: Int, width: Int, overflow: String) raises -> Int:
    if overflow == "clip":
        return clip_unsigned(value, width)
    if overflow == "wrap":
        return low_bits(value, width)
    raise Error("overflow must be clip or wrap")


def pack_fields[
    n: Int
](
    widths: Array[Int, n],
    values: Array[Int, n],
    overflow: String = "clip",
) raises -> Array[UInt8, PACK_BYTES]:
    """Pack ``n`` unsigned fields, LSB first, into a zeroed 8-byte buffer.

    ``overflow`` defaults to ``clip``. Pass ``"wrap"`` to keep the low bits.
    """
    var out = Array[UInt8, PACK_BYTES](fill=UInt8(0))
    var cursor = 0
    for i in range(n):
        var width = widths[i]
        var bits = _field_bits(values[i], width, overflow)
        for bit in range(width):
            if cursor >= PACK_BITS:
                raise Error("pack buffer is 8 bytes")
            var bit_val = (bits >> bit) & 1
            if bit_val != 0:
                var index = cursor // 8
                var shift = cursor % 8
                out[index] = out[index] | UInt8(1 << shift)
            cursor += 1
    return out^


def main() raises:
    """Pack codec vector ``u12`` (2748 -> ``bc0a``) and fail if it drifts."""
    var widths = Array[Int, 1](fill=12)
    var values = Array[Int, 1](fill=2748)
    var packed = pack_fields[1](widths, values)
    if Int(packed[0]) != 0xBC or Int(packed[1]) != 0x0A:
        raise Error("u12 vector bc0a mismatch")
    print("u12 2748 packs as bc0a")
