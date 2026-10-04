"""LSB-first unsigned bit packer for the Mojo toolchain smoke test.

Python ``astra.codec`` is still the packer the service calls. This module is
the small kernel CI compiles with Modular's published Mojo image. Out-of-range
integers keep the low bits of the field width, matching the default
``pack(..., overflow="wrap")``.

The byte checks in ``test_bitpack.mojo`` are the transcribed vectors ``u8``,
``u12``, ``u12_after_bool``, and ``u8_out_of_range_wraps`` from
``tests/data/codec_vectors.json``.
"""

from std.collections import Array

comptime PACK_BYTES = 8
comptime PACK_BITS = PACK_BYTES * 8


def low_bits(value: Int, width: Int) -> Int:
    """Keep the low ``width`` bits of ``value``."""
    return value & ((1 << width) - 1)


def bool_bit(value: Int) -> Int:
    """Bool fields keep the low bit. Two becomes zero; three becomes one."""
    return value & 1


def pack_fields[
    n: Int
](widths: Array[Int, n], values: Array[Int, n]) raises -> Array[UInt8, PACK_BYTES]:
    """Pack ``n`` unsigned fields, LSB first, into a zeroed 8-byte buffer."""
    var out = Array[UInt8, PACK_BYTES](fill=UInt8(0))
    var cursor = 0
    for i in range(n):
        var width = widths[i]
        var bits = low_bits(values[i], width)
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
