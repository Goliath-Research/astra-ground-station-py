"""Mojo checks against transcribed Python codec vectors.

Run with ``mojo run -I mojo mojo/test_bitpack.mojo``.
The default pack saturates. ``overflow="wrap"`` reproduces the one transcribed
vector that stored the low bits.
"""

from bitpack import bool_bit, clip_bool, clip_unsigned, low_bits, pack_fields

from std.collections import Array
from std.testing import TestSuite, assert_equal


def test_u8_vector_a5() raises:
    var widths = Array[Int, 1](fill=8)
    var values = Array[Int, 1](fill=165)
    var packed = pack_fields[1](widths, values)
    # tests/data/codec_vectors.json id "u8", expected_hex "a5".
    assert_equal(Int(packed[0]), 0xA5)
    assert_equal(Int(packed[1]), 0)


def test_u8_default_clips_300_to_ff() raises:
    var widths = Array[Int, 1](fill=8)
    var high = Array[Int, 1](fill=300)
    var low = Array[Int, 1](fill=-1)
    var top = Array[Int, 1](fill=255)
    var zero = Array[Int, 1](fill=0)
    # Default is clip: 300 as u8 saturates to 255 (ff), and a negative clamps to 0.
    assert_equal(Int(pack_fields[1](widths, high)[0]), 0xFF)
    assert_equal(Int(pack_fields[1](widths, low)[0]), 0x00)
    assert_equal(Int(pack_fields[1](widths, top)[0]), 0xFF)
    assert_equal(Int(pack_fields[1](widths, zero)[0]), 0x00)
    assert_equal(clip_unsigned(300, 8), 255)
    assert_equal(clip_unsigned(-1, 8), 0)
    assert_equal(clip_unsigned(0, 8), 0)
    assert_equal(clip_unsigned(255, 8), 255)


def test_u8_wrap_reproduces_transcribed_vector() raises:
    var widths = Array[Int, 1](fill=8)
    var values = Array[Int, 1](fill=300)
    var packed = pack_fields[1](widths, values, "wrap")
    # tests/data/codec_vectors.json id "u8_out_of_range_wraps": 300 -> "2c".
    assert_equal(Int(packed[0]), 0x2C)
    assert_equal(low_bits(300, 8), 0x2C)


def test_u12_vector_bc0a() raises:
    var widths = Array[Int, 1](fill=12)
    var values = Array[Int, 1](fill=2748)
    var packed = pack_fields[1](widths, values)
    # tests/data/codec_vectors.json id "u12", expected_hex "bc0a".
    assert_equal(Int(packed[0]), 0xBC)
    assert_equal(Int(packed[1]), 0x0A)


def test_u12_after_bool_vector() raises:
    var widths = Array[Int, 2](fill=0)
    widths[0] = 1
    widths[1] = 12
    var values = Array[Int, 2](fill=0)
    values[0] = clip_bool(1)
    values[1] = 2748
    var packed = pack_fields[2](widths, values)
    # tests/data/codec_vectors.json id "u12_after_bool", expected_hex "7915".
    assert_equal(Int(packed[0]), 0x79)
    assert_equal(Int(packed[1]), 0x15)


def test_bool_clips_nonzero_to_one() raises:
    assert_equal(clip_bool(0), 0)
    assert_equal(clip_bool(1), 1)
    assert_equal(clip_bool(2), 1)
    assert_equal(clip_bool(-4), 1)
    # Legacy wrap keeps the low bit.
    assert_equal(bool_bit(2), 0)
    assert_equal(bool_bit(3), 1)


def main() raises:
    TestSuite.discover_tests[__functions_in_module()]().run()
