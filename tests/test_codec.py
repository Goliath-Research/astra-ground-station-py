"""Golden payloads for the packer.

``CODEC_SPEC.md`` and ``codec_vectors.json`` from astra-ground-station PR #6
were not on disk, so the 29 source-verified vectors were not loaded and
these tests do not cite Delphi line numbers. The expected bytes follow the
rules that spec was described as stating, named by unit and routine:

- ``AstraVarPacket.pas`` ``TBitStream.SaveBit`` / ``SavePacket``: zero the
  buffer, then concatenate fields with no padding. LSB first within a byte,
  little-endian across bytes. ``u12`` ``0x0ABC`` is ``bc0a``; the same value
  after a true bool is ``7915``.
- ``AstraVarPacket.pas`` ``SaveValue``: out-of-range integers keep the low
  bits (300 as ``u8`` is ``2c``). Null becomes 0. Q types are the raw
  integer (``i32q8`` 256 stays 256). ``f32`` / ``f64`` are IEEE-754,
  including NaN.
- ``AstraVarPacket.pas`` ``LoadFieldOvrs``: one ``ovr_`` bool per field,
  appended after the whole flattened record. An array gets one override
  bit, not one per element. Nested records (type id > 100) flatten in
  field order; each element's own override bits stay with that element.
- ``AstraNetPacket.pas`` ``GetIdPayload`` and ``GetDeviceT_MS``: a datagram
  is a signed int32 little-endian packet id plus the payload. ``t_ms`` is
  the first four payload bytes. No checksum.
- ``AstraInpPopper.pas`` ``SyncWrite``: ``0`` becomes ``1e-7`` for OPC
  Single/Double only. That substitution is not on the wire.
"""

import math
import struct

import pytest

from astra.codec import (
    CodecError,
    Field,
    device_t_ms,
    encoded_size,
    flatten,
    pack,
    pack_id_payload,
    unpack,
    unpack_id_payload,
)
from tests.savebit_reference import save_bits


def test_bool_false_is_a_cleared_byte() -> None:
    # SaveBit of a 1-bit false, then the byte pad from ceiling(bits/8).
    fields = (Field("flag", 1),)
    assert pack(fields, [False]) == b"\x00"
    assert unpack(fields, b"\x00") == (False,)


def test_bool_true_sets_only_bit_0() -> None:
    fields = (Field("flag", 1),)
    assert pack(fields, [True]) == b"\x01"
    assert save_bits([(1, 1)]) == b"\x01"


def test_two_bools_share_a_byte() -> None:
    fields = (Field("a", 1), Field("b", 1))
    assert pack(fields, [True, True]) == b"\x03"


def test_u8_is_one_byte() -> None:
    fields = (Field("b", 2),)
    assert pack(fields, [0xA5]) == b"\xa5"


def test_u12_aligned_is_little_endian_low_twelve_bits() -> None:
    # SavePacket of u12 0x0ABC, no leading bits. Low byte 0xBC, high nibble 0xA.
    fields = (Field("sample", 3),)
    assert pack(fields, [0x0ABC]) == bytes.fromhex("bc0a")
    assert unpack(fields, bytes.fromhex("bc0a")) == (0xABC,)


def test_u12_0xabc_after_a_true_bool() -> None:
    # SavePacket concatenates with no pad. bool true, then u12 0x0ABC.
    # byte0 bits 0..7 = 1,0,0,1,1,1,1,0 = 0x79. byte1 = 0x15.
    fields = (Field("flag", 1), Field("sample", 3))
    assert pack(fields, [True, 0x0ABC]) == bytes.fromhex("7915")
    assert unpack(fields, bytes.fromhex("7915")) == (True, 0xABC)


def test_u12_at_bit_offset_4() -> None:
    # Four bools occupy bits 0..3. The u12 starts at bit 4, which is the
    # case the Win64 harness was asked to record. 0xFFF is twelve 1 bits.
    # byte0: bits 0..3 = 0, bits 4..7 = 1 -> 0xF0. byte1 = 0xFF.
    fields = (
        Field("n0", 1),
        Field("n1", 1),
        Field("n2", 1),
        Field("n3", 1),
        Field("sample", 3),
    )
    payload = pack(fields, [False, False, False, False, 0xFFF])
    assert payload == bytes.fromhex("f0ff")
    assert save_bits([(1, 0), (1, 0), (1, 0), (1, 0), (12, 0xFFF)]) == payload
    assert unpack(fields, payload) == (False, False, False, False, 0xFFF)


def test_u12_0xabc_after_four_set_bits() -> None:
    # 0xABC bits from LSB: 0011 1101 0101, written at bit 4.
    # byte0 = 0b1100_1111 = 0xCF, byte1 = 0b1010_1011 = 0xAB.
    fields = (Field("pad", 1, qty=4), Field("sample", 3))
    payload = pack(fields, [True, True, True, True, 0xABC])
    assert payload == bytes.fromhex("cfab")
    assert encoded_size(fields) == 2


def test_u16_and_u32_are_little_endian() -> None:
    assert pack((Field("w", 4),), [0x1234]) == bytes.fromhex("3412")
    assert pack((Field("d", 5),), [0x89ABCDEF]) == bytes.fromhex("efcdab89")


def test_signed_integers_are_twos_complement() -> None:
    # SaveValue of shortint / smallint / longint.
    assert pack((Field("b", 6),), [-1]) == b"\xff"
    assert pack((Field("b", 6),), [-128]) == b"\x80"
    assert pack((Field("w", 7),), [-2]) == bytes.fromhex("feff")
    assert pack((Field("d", 8),), [-2147483648]) == bytes.fromhex("00000080")
    assert unpack((Field("d", 8),), bytes.fromhex("00000080")) == (-2147483648,)


def test_q_types_are_not_shifted() -> None:
    # SaveValue stores the raw integer. i32q8 value 256 is the integer 256.
    assert pack((Field("q", 11),), [256]) == bytes.fromhex("00010000")
    assert pack((Field("q", 12),), [256]) == bytes.fromhex("00010000")
    assert pack((Field("q", 11),), [-2]) == bytes.fromhex("feffffff")
    assert pack((Field("q", 13),), [0xFF]) == b"\xff"
    assert pack((Field("q", 14),), [0x8000]) == bytes.fromhex("0080")


def test_f32_and_f64_are_ieee754_little_endian() -> None:
    # struct '<f' / '<d' of the in-memory Single / Double, then SaveBit.
    assert pack((Field("x", 9),), [1.0]) == struct.pack("<f", 1.0)
    assert pack((Field("x", 10),), [-0.0]) == struct.pack("<d", -0.0)
    assert unpack((Field("x", 10),), struct.pack("<d", -0.0)) == (-0.0,)
    # A wire zero stays zero. SyncWrite's 1e-7 substitution is not applied.
    assert pack((Field("x", 10),), [0.0]) == b"\x00" * 8


def test_nan_payloads_are_ieee754() -> None:
    nan32 = struct.pack("<f", float("nan"))
    restored32 = unpack((Field("x", 9),), nan32)
    assert pack((Field("x", 9),), [float("nan")]) == nan32
    assert isinstance(restored32[0], float) and math.isnan(restored32[0])
    nan64 = struct.pack("<d", float("nan"))
    restored64 = unpack((Field("x", 10),), nan64)
    assert pack((Field("x", 10),), [float("nan")]) == nan64
    assert isinstance(restored64[0], float) and math.isnan(restored64[0])


def test_bool_and_u8_share_bytes() -> None:
    # bool true, then u8 0xAA starting at bit 1.
    # 0xAA LSB-first is 0,1,0,1,0,1,0,1. byte0 = 0x55, leftover bit = 1.
    fields = (Field("flag", 1), Field("b", 2))
    assert pack(fields, [True, 0xAA]) == bytes.fromhex("5501")
    assert unpack(fields, bytes.fromhex("5501")) == (True, 0xAA)


def test_array_repeats_the_scalar() -> None:
    fields = (Field("b", 2, qty=3),)
    assert pack(fields, [1, 2, 3]) == b"\x01\x02\x03"
    assert [item.name for item in flatten(fields)] == ["b_0", "b_1", "b_2"]


def test_override_bit_is_appended_after_the_values() -> None:
    # One u8 and one later u8. Only the first has Override. LoadFieldOvrs
    # contributes a single trailing bit, not a bit after the first field
    # and not one bit per array element.
    fields = (Field("a", 2, override=True), Field("b", 2))
    payload = pack(fields, [0x01, 0x00, True])
    assert payload == bytes.fromhex("010001")
    assert [item.name for item in flatten(fields)] == ["a", "b", "ovr_a"]
    assert unpack(fields, payload) == (1, 0, True)


def test_override_is_one_bit_for_the_whole_array() -> None:
    fields = (Field("a", 2, qty=2, override=True),)
    payload = pack(fields, [0x10, 0x20, False])
    assert payload == b"\x10\x20\x00"
    assert encoded_size(fields) == 3


def test_nested_record_is_packed_inline_without_a_byte_pad() -> None:
    # TypeID > 100 flattens. Child is u8 0xFF then bool true (9 bits),
    # then the parent's following u8 starts at bit 9.
    nested = Field("rec", 101, fields=(Field("a", 2), Field("flag", 1)))
    fields = (nested, Field("c", 2))
    payload = pack(fields, [0xFF, True, 0x01])
    assert payload == bytes.fromhex("ff0300")
    assert unpack(fields, payload) == (0xFF, True, 0x01)
    names = [item.name for item in flatten(fields)]
    assert names == ["rec_a", "rec_flag", "c"]


def test_array_of_nested_records_keeps_each_elements_override() -> None:
    # qty does not byte-align elements. Each element ends with its own ovr bit.
    nested = Field("rec", 200, qty=2, fields=(Field("x", 2, override=True),))
    assert [item.name for item in flatten((nested,))] == [
        "rec_0_x",
        "ovr_rec_0_x",
        "rec_1_x",
        "ovr_rec_1_x",
    ]
    payload = pack((nested,), [0x01, False, 0x02, True])
    assert payload == bytes.fromhex("010402")
    assert unpack((nested,), payload) == (0x01, False, 0x02, True)


def test_nested_array_has_one_override_bit() -> None:
    nested = Field("rec", 200, qty=2, override=True, fields=(Field("x", 2),))
    assert [item.name for item in flatten((nested,))] == ["rec_0_x", "rec_1_x", "ovr_rec"]
    assert pack((nested,), [0x11, 0x22, True]) == bytes.fromhex("112201")


def test_nested_override_stays_inside_the_child() -> None:
    # Child LoadFieldOvrs runs before the parent continues. x = 0,
    # ovr = 1, then the parent has no further fields. 8 zero bits + 1.
    nested = Field(
        "rec",
        200,
        fields=(Field("x", 2, override=True),),
    )
    payload = pack((nested,), [0x00, True])
    assert payload == bytes.fromhex("0001")
    assert [item.name for item in flatten((nested,))] == ["rec_x", "ovr_rec_x"]


def test_id_payload_is_a_signed_little_endian_integer() -> None:
    # GetIdPayload / SetIdPayload. Id 1, payload begins with t_ms = 2.
    payload = struct.pack("<i", 2)
    datagram = pack_id_payload(1, payload)
    assert datagram == struct.pack("<i", 1) + payload
    assert unpack_id_payload(datagram) == (1, payload)
    assert device_t_ms(payload) == 2
    assert unpack_id_payload(pack_id_payload(-1, b""))[0] == -1


def test_out_of_range_integers_keep_the_low_bits() -> None:
    # 300 = 0x12C. SaveValue keeps the low 8 bits: 0x2C.
    assert pack((Field("b", 2),), [300]) == bytes.fromhex("2c")
    assert unpack((Field("b", 2),), bytes.fromhex("2c")) == (0x2C,)
    # 0x1000 keeps the low 12 bits, which are zero.
    assert pack((Field("sample", 3),), [0x1000]) == bytes.fromhex("0000")
    # -200 as i8 keeps 0x38. The sign bit is clear, so unpack is +56.
    assert pack((Field("b", 6),), [-200]) == bytes.fromhex("38")
    assert unpack((Field("b", 6),), bytes.fromhex("38")) == (56,)
    # A bool field is one bit. 3 keeps the low bit.
    assert pack((Field("flag", 1),), [3]) == b"\x01"
    assert pack((Field("flag", 1),), [2]) == b"\x00"


def test_null_packs_as_zero() -> None:
    assert pack((Field("b", 2),), [None]) == b"\x00"
    assert pack((Field("flag", 1),), [None]) == b"\x00"
    assert unpack((Field("flag", 1),), pack((Field("flag", 1),), [None])) == (False,)
    assert pack((Field("x", 9),), [None]) == struct.pack("<f", 0.0)
    assert pack((Field("x", 10),), [None]) == struct.pack("<d", 0.0)
    assert pack((Field("q", 11),), [None]) == b"\x00" * 4


def test_short_buffers_and_oversized_packet_ids_are_rejected() -> None:
    with pytest.raises(CodecError):
        unpack((Field("b", 2),), b"")
    with pytest.raises(CodecError):
        pack_id_payload(0x80000000, b"")
    with pytest.raises(CodecError):
        device_t_ms(b"\x00\x00")
    with pytest.raises(CodecError):
        pack((Field("b", 2),), [True])


def test_empty_layout_is_empty() -> None:
    assert pack((), []) == b""
    assert unpack((), b"") == ()
    assert encoded_size(()) == 0
