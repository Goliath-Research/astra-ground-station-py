import pytest

from astra.codec import CodecError, pack
from astra.settings import stage_count as configured_stage_count
from astra.tmoip import (
    MinorFrameEncoder,
    StageDecoder,
    StreamPacket,
    frame_due,
    irig106_fields,
    minor_frame_packet_id,
    reassemble,
    stage_count,
    stage_port,
    stage_ports,
)
from astra.tmoip.__main__ import main

_RATES = (0, 1, 10, 100, 200)
_INCLUDED = {
    0: {0, 1, 10, 100, 200},
    1: {0, 200},
    2: {0, 100, 200},
    20: {0, 10, 100, 200},
    200: {0, 1, 10, 100, 200},
}


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


def test_irig_rate_zero_is_a_divide_by_zero() -> None:
    with pytest.raises(ZeroDivisionError):
        frame_due(0, 1, 0)


@pytest.mark.parametrize(
    ("sequence", "rate"),
    [(sequence, rate) for sequence in sorted(_INCLUDED) for rate in _RATES],
    ids=[f"seq{sequence}-rate{rate}" for sequence in sorted(_INCLUDED) for rate in _RATES],
)
def test_rate_table_at_irig_200(sequence: int, rate: int) -> None:
    # (Sequence = 0) or (Sequence * rate mod 200 = 0), before Sequence increments.
    assert frame_due(sequence, rate, 200) is (rate in _INCLUDED[sequence])


def test_encoder_builds_the_two_fixture_minor_frames() -> None:
    # Packet 0x01020304, enc size 4. The 4-byte field takes the id first
    # (04 03 02 01) and the zero payload on the next subframe. No id prefix,
    # no checksum, listen port 2357+stage.
    encoder = MinorFrameEncoder(
        (StreamPacket(16909060, 100, 4),),
        irig_rate=200,
        row_id=1,
        stage=1,
        environ={},
    )
    first = encoder.tick()
    assert first.payload == bytes.fromhex("010100000004030201")
    assert first.port == 2358
    assert first.sf_id == 1
    assert encoder.sequence == 1
    second = encoder.tick()
    assert second.payload == bytes.fromhex("020100000000000000")
    assert second.sf_id == 2
    assert second.row_id == 1
    assert encoder.sequence == 1
    assert len(first.payload) == len(pack(irig106_fields(), [1, 1, 4, 3, 2, 1]))


def test_next_build_cycle_advances_the_row_and_reassembles() -> None:
    # Rate 200 is due at every sequence. Each cycle is an id plus 4 zero
    # payload bytes, split across two minor frames. After the buffer drains,
    # SubFrameID restarts at 1 on the next row. The same row with sf_id 1
    # again would be a gap and PushStream would drop the later cycles.
    encoder = MinorFrameEncoder(
        (StreamPacket(16909060, 200, 4),),
        irig_rate=200,
        row_id=1,
        stage=1,
        environ={},
    )
    decoder = StageDecoder(1, {16909060: 4}, estimated_row_id=1, environ={})
    frames = [encoder.tick() for _ in range(4)]
    assert [(frame.sf_id, frame.row_id, frame.payload.hex()) for frame in frames] == [
        (1, 1, "010100000004030201"),
        (2, 1, "020100000000000000"),
        (1, 2, "010200000004030201"),
        (2, 2, "020200000000000000"),
    ]
    for frame in frames:
        reassemble(frame.payload, decoder)
    body = bytes.fromhex("0403020100000000")
    assert [item.payload for item in decoder.forwarded] == [body, body]


def test_same_row_subframe_restart_stays_a_gap() -> None:
    decoder = StageDecoder(1, {16909060: 4}, estimated_row_id=1, environ={})
    decoder.udp_read(bytes.fromhex("010100000004030201"))
    decoder.udp_read(bytes.fromhex("020100000000000000"))
    assert len(decoder.forwarded) == 1
    decoder.udp_read(bytes.fromhex("010100000004030201"))
    decoder.udp_read(bytes.fromhex("020100000000000000"))
    assert len(decoder.forwarded) == 1
    assert decoder.last_row_id == 1
    assert decoder._skip_row is True


def test_decoder_reassembles_the_fixture_stream() -> None:
    encoder = MinorFrameEncoder(
        (StreamPacket(16909060, 100, 4),),
        irig_rate=200,
        row_id=1,
        stage=1,
        environ={},
    )
    decoder = StageDecoder(1, {16909060: 4}, estimated_row_id=1, environ={})
    reassemble(encoder.tick().payload, decoder)
    assert decoder.forwarded == []
    reassemble(encoder.tick().payload, decoder)
    assert decoder.logged[0].packet_id == 106
    assert [(item.host, item.port, item.payload) for item in decoder.forwarded] == [
        ("127.0.0.1", 2357, bytes.fromhex("0403020100000000"))
    ]


def test_decoder_ignores_a_subframe_gap_until_the_next_row() -> None:
    fields = irig106_fields(stream_qty=2)
    decoder = StageDecoder(1, {7: 0}, estimated_row_id=5, fields=fields, environ={})
    decoder.udp_read(pack(fields, [1, 1, 7, 0]))
    assert decoder.forwarded == []
    decoder.udp_read(pack(fields, [3, 1, 0, 0]))
    decoder.udp_read(pack(fields, [4, 1, 9, 9]))
    assert decoder.forwarded == []
    decoder.udp_read(pack(fields, [1, 2, 0, 0]))
    assert len(decoder.forwarded) == 1
    assert decoder.forwarded[0].payload == bytes.fromhex("07000000")


def test_decoder_drops_a_row_rewind_a_jump_and_sf_id_above_16() -> None:
    fields = irig106_fields()
    decoder = StageDecoder(2, {7: 0}, estimated_row_id=1, environ={})
    decoder.udp_read(pack(fields, [1, 1, 0, 0, 0, 0]))
    before = len(decoder.forwarded)
    decoder.udp_read(pack(fields, [1, 0, 7, 0, 0, 0]))
    decoder.udp_read(pack(fields, [1, 12, 7, 0, 0, 0]))
    decoder.udp_read(pack(fields, [17, 1, 7, 0, 0, 0]))
    assert len(decoder.forwarded) == before
    assert decoder.logged[-1].packet_id == 206


def test_decoder_skips_an_unknown_or_non_positive_id() -> None:
    fields = irig106_fields()
    decoder = StageDecoder(1, {7: 0}, estimated_row_id=1, environ={})
    decoder.udp_read(pack(fields, [1, 1, 0, 0, 0, 0]))
    decoder.udp_read(pack(fields, [2, 1, 7, 0, 0, 0]))
    assert decoder.forwarded[-1].payload == bytes.fromhex("07000000")
    assert decoder.forwarded[-1].port == 2357


def test_bridge_port_override_is_where_the_decoder_sends() -> None:
    decoder = StageDecoder(1, {7: 0}, environ={"ASTRA_BRIDGE_PORT": "2400"})
    decoder.push_buffer_to_packet(bytes.fromhex("07000000"))
    assert decoder.forwarded[0].port == 2400
    assert decoder.forwarded[0].host == "127.0.0.1"


def test_oversized_stream_packet_id_is_rejected() -> None:
    with pytest.raises(CodecError):
        StreamPacket(0x80000000, 1, 0)
