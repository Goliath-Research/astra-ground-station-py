import pytest

from astra.codec import CodecError
from astra.settings import stage_count as configured_stage_count
from astra.tmoip import (
    MinorFrameLayout,
    build_minor_frame,
    frame_due,
    minor_frame_packet_id,
    parse_minor_frame,
    reassemble,
    stage_count,
    stage_port,
    stage_ports,
)
from astra.tmoip.__main__ import main


def test_default_stage_ports_follow_the_delphi_decoder() -> None:
    assert stage_count({}) == 2
    assert stage_port(1, {}) == 2358
    assert stage_port(2, {}) == 2359
    assert stage_ports({}) == (2358, 2359)
    assert main(["--check"]) == 0


def test_minor_frame_ids_follow_stage_count() -> None:
    # TAstraDecoder: packet id 100 * (stage - 1) + 106. The count is settings.
    count = configured_stage_count({})
    assert count == 2
    assert [minor_frame_packet_id(stage) for stage in range(1, count + 1)] == [106, 206]
    assert minor_frame_packet_id(3) == 306


def test_encoder_rate_rule() -> None:
    # AstraTMEncoder, before Sequence increments:
    # (Sequence = 0) or (Sequence * packetRate mod irigRate = 0).
    assert frame_due(0, 100, 200)
    assert frame_due(0, 1, 1)
    assert not frame_due(1, 100, 200)
    assert frame_due(2, 100, 200)
    assert frame_due(5, 0, 200)


def test_minor_frame_uses_configurable_widths_and_no_checksum() -> None:
    # sf_id and row_id widths come from the database. This is a fixture
    # layout, not a production row. The encoder writes int32 LE id 7 and
    # zeros the rest of a 6-byte stream. No checksum byte is appended.
    layout = MinorFrameLayout(sf_id_bits=8, row_id_bits=8, packet_stream_bytes=6)
    frame = build_minor_frame(1, 2, 7, layout)
    assert frame == bytes.fromhex("0102070000000000")
    assert parse_minor_frame(frame, layout) == (1, 2, 7, bytes.fromhex("070000000000"))


def test_minor_frame_fields_are_not_byte_aligned() -> None:
    # 4-bit sf_id = 1, then 4-bit row_id = 2, share the first byte as 0x21.
    layout = MinorFrameLayout(sf_id_bits=4, row_id_bits=4, packet_stream_bytes=4)
    frame = build_minor_frame(1, 2, 7, layout)
    assert frame == bytes.fromhex("2107000000")
    assert parse_minor_frame(frame, layout) == (1, 2, 7, bytes.fromhex("07000000"))


def test_minor_frame_stream_can_start_mid_byte() -> None:
    # 4-bit sf_id = 1, 8-bit row_id = 0xAB, then the id continues at bit 12.
    layout = MinorFrameLayout(sf_id_bits=4, row_id_bits=8, packet_stream_bytes=4)
    frame = build_minor_frame(1, 0xAB, 1, layout)
    # row's high nibble shares byte 1 with the start of the int32 id.
    assert frame == bytes.fromhex("b11a00000000")
    assert parse_minor_frame(frame, layout) == (1, 0xAB, 1, bytes.fromhex("01000000"))


def test_minor_frame_rejects_a_short_stream_and_an_oversized_id() -> None:
    with pytest.raises(ValueError):
        MinorFrameLayout(sf_id_bits=8, row_id_bits=8, packet_stream_bytes=3)
    layout = MinorFrameLayout(sf_id_bits=8, row_id_bits=8, packet_stream_bytes=4)
    with pytest.raises(CodecError):
        build_minor_frame(1, 2, 0x80000000, layout)


def test_reassembly_is_not_ported() -> None:
    with pytest.raises(NotImplementedError, match="TMoIP"):
        reassemble(b"")
