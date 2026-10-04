"""Codec facts taken from the migrated Astra config database.

The numbers are the census in ``docs/CODEC_DB_ANSWERS.md``. The tests do not
open a database connection.
"""

import json
from dataclasses import replace
from pathlib import Path

from astra.codec import (
    Field,
    encoded_size,
    flatten,
    pack,
    packed_enc_bytes,
    sort_fields,
    transform_output,
    unpack,
)
from astra.codec.python_pack import Value
from astra.codec.types import FlatField, encoded_bit_count
from astra.opcua import LEGACY_OPC_DA_SERVER
from astra.settings import DEFAULT_BRIDGE_PORT, DEFAULT_STAGE_COUNT
from astra.tmoip import (
    CALCULATED_INPUT_PACKETS,
    CONFIG_FREQUENCIES_HZ,
    DEFAULT_ENCODER_RATE_HZ,
    IRIG106_PACKET_IDS,
    MAX_SF_ID,
    STORED_INPUT_PACKETS,
    MinorFrameEncoder,
    StreamPacket,
    irig106_fields,
    minor_frame_packet_id,
    spec_fixture_fields,
)
from astra.tmoip.irig import IRIG106_BITS, IRIG106_ENC_BYTES, PACKET_STREAM_BYTES

_FIXTURE = Path(__file__).parent / "data" / "irig106_fixture.json"

# leaf bits, override leaves, stored-or-recalculated EncSize. Record-level
# Override does not appear: all 186 Override rows are leaves.
_PACKET_SIZES = (
    (1, "L2R", "L2R", 4895, 148, 631),
    (2, "R2L", "R2L", 6017, 0, 753),
    (5, "PSTL2R", "L2R", 674, 11, 86),
    (6, "PSTR2L", "R2L", 401, 0, 51),
    (7, "PSTL2RSeq", "L2R", 7520, 1, 941),
    (10, "EngineL2R", "L2R", 2167, 12, 273),
    (11, "EngineR2L", "R2L", 1038, 14, 132),
    (101, "L2R", "L2R", 4895, 148, 631),
    (102, "R2L", "R2L", 6017, 0, 753),
    (107, "PSTR2LD", "R2L", 401, 0, 51),
    (1060, "TMstats1", "R2L", 384, 0, 48),
    (1061, "IRIG106", "R2L", 2792, 0, 349),
    (1062, "IRIG106", "R2L", 2792, 0, 349),
    (1063, "TMstats2", "R2L", 384, 0, 48),
)

_LEAF_OFFSETS = {
    "fap_type": 0,
    "fap_seq_counter_0": 8,
    "fap_bytes_in_packet_0": 21,
    "fap_zeroes12_0": 32,
    "fap_IRIG_time_status_IRIG_present": 44,
    "fap_IRIG_time_status_Reserved_0": 45,
    "fap_frame_sync_status_Reserved1": 52,
    "fap_frame_sync_status_Search": 63,
    "fap_milliseconds_in_the_day": 64,
    "fap_Subframe_id_0": 96,
    "fap_words_per_minor_frame": 106,
    "fap_bits_per_word_0": 122,
    "fap_bitrate": 128,
    "fsp": 160,
    "sf_id": 192,
    "row_id": 200,
    "range_variables_0": 232,
    "packet_stream_0": 1192,
}


def test_packed_bits_match_stored_encsize_for_every_packet() -> None:
    # eMaster L2R: 4895 leaf bits + 148 override bits = 5043 bits = 631 bytes.
    # EngineR2L is the only R2L packet with override bits.
    assert packed_enc_bytes(4895, 148) == 631
    assert 4895 + 148 == 5043
    r2l_with_override = [
        name
        for _packet_id, name, direction, _bits, overrides, _size in _PACKET_SIZES
        if direction == "R2L" and overrides
    ]
    assert r2l_with_override == ["EngineR2L"]
    assert packed_enc_bytes(1038, 14) == 132
    for _packet_id, _name, _direction, leaf_bits, overrides, enc_size in _PACKET_SIZES:
        assert packed_enc_bytes(leaf_bits, overrides) == enc_size
    assert encoded_size(irig106_fields()) == packed_enc_bytes(IRIG106_BITS, 0) == IRIG106_ENC_BYTES


def test_irig106_default_layout_is_349_bytes_at_the_database_offsets() -> None:
    fields = irig106_fields()
    layout = [item for item in flatten(fields) if item.role == "value"]
    assert encoded_bit_count(fields) == IRIG106_BITS
    assert encoded_size(fields) == IRIG106_ENC_BYTES
    assert IRIG106_BITS % 8 == 0
    assert len(layout) == 399
    assert _primitive_leaves(fields) == 28
    assert fields[3].name == "row_id" and fields[3].type_id == 5
    offsets = _bit_offsets(layout)
    assert offsets == {**offsets, **_LEAF_OFFSETS}
    for name, bit in _LEAF_OFFSETS.items():
        assert offsets[name] == bit
    assert offsets["packet_stream_0"] // 8 == 149
    assert offsets["sf_id"] // 8 == 24
    assert offsets["row_id"] // 8 == 25


def test_irig106_fixture_vectors_pack_and_round_trip() -> None:
    document = json.loads(_FIXTURE.read_text())
    layout = document["layouts"]["irig106_real"]
    flat = tuple(Field(entry["name"], entry["type_id"], qty=entry["qty"]) for entry in layout)
    nested = irig106_fields()
    assert [item.name for item in flatten(flat)] == [item.name for item in flatten(nested)]
    assert len(document["vectors"]) == 6
    for vector in document["vectors"]:
        values = _expand(layout, vector["values"])
        expected = bytes.fromhex(vector["expected_hex"])
        assert len(expected) == vector["byte_length"] == IRIG106_ENC_BYTES
        assert pack(flat, values) == expected
        assert pack(nested, values) == expected
        assert pack(nested, unpack(nested, expected)) == expected
    probe = document["vectors"][-1]
    unpacked = unpack(nested, bytes.fromhex(probe["expected_hex"]))
    row_at = next(index for index, item in enumerate(flatten(nested)) if item.name == "row_id")
    assert unpacked[row_at] == 2309737967
    assert probe["values"]["row_id"] == 2309737967


def test_encoder_matches_the_database_minor_frame_vectors() -> None:
    document = json.loads(_FIXTURE.read_text())
    by_id = {vector["id"]: vector for vector in document["vectors"]}
    tmstats = by_id["irig106_stage1_tmstats1_seq0"]
    encoder = MinorFrameEncoder(
        (StreamPacket(1060, enc_size=48, send=True),),
        irig_rate=tmstats["irig_rate_hz"],
        environ={},
    )
    frame = encoder.tick()
    assert frame.payload.hex() == tmstats["expected_hex"]
    assert (frame.sf_id, frame.row_id, frame.port) == (1, 1, 2358)
    assert len(frame.payload) == IRIG106_ENC_BYTES

    r2l = MinorFrameEncoder((StreamPacket(2, enc_size=753, send=True),), environ={})
    frames = [r2l.tick() for _ in range(4)]
    for index, frame in enumerate(frames, start=1):
        vector = by_id[f"irig106_stage1_r2l_frame_{index}_of_4"]
        assert frame.payload.hex() == vector["expected_hex"]
        assert (frame.sf_id, frame.row_id) == (index, 1)
    nxt = r2l.tick()
    assert (nxt.sf_id, nxt.row_id) == (1, 2)


def test_send_defaults_off_and_the_encoder_rate_defaults_to_100() -> None:
    idle = StreamPacket(1060, enc_size=48)
    assert idle.send is False
    assert idle.packet_rate == 0
    quiet = MinorFrameEncoder((idle,), environ={})
    assert quiet.tick().payload[149:] == bytes(PACKET_STREAM_BYTES)

    fields = spec_fixture_fields()
    encoder = MinorFrameEncoder(
        (StreamPacket(7, packet_rate=100, enc_size=0, send=True),),
        fields=fields,
        environ={},
    )
    assert encoder.tick().payload == bytes.fromhex("010100000007000000")
    # Sequence 1 includes rate 100 when the base rate is 100, and skips it at 200.
    assert encoder.tick().payload == bytes.fromhex("010200000007000000")
    assert DEFAULT_ENCODER_RATE_HZ == 100
    assert CONFIG_FREQUENCIES_HZ == (200, 1, 10, 400)


def test_input_packet_list_and_the_major_frame_ceiling() -> None:
    assert STORED_INPUT_PACKETS == (
        (2, "R2L", 753),
        (6, "PSTR2L", 51),
        (107, "PSTR2LD", 51),
        (1060, "TMstats1", 48),
        (1061, "IRIG106", 349),
        (1062, "IRIG106", 349),
        (1063, "TMstats2", 48),
    )
    assert CALCULATED_INPUT_PACKETS == ((11, "EngineR2L", 132), (102, "R2L", 753))
    assert MAX_SF_ID * PACKET_STREAM_BYTES == 3200
    assert minor_frame_packet_id(1) == 106
    assert minor_frame_packet_id(2) == 206
    assert IRIG106_PACKET_IDS == {1: 1061, 2: 1062}
    assert minor_frame_packet_id(1) != IRIG106_PACKET_IDS[1]


def test_l2r_pack_does_not_scale_or_transform() -> None:
    # Logged L2R integers: heaterHigh 40, heReguHigh 70, parkerStepSustDuty 255.
    fields = (
        Field("heaterHigh", 11),
        Field("heReguHigh", 11),
        Field("parkerStepSustDuty", 13),
    )
    payload = pack(fields, [40, 70, 255])
    assert payload == (40).to_bytes(4, "little") + (70).to_bytes(4, "little") + bytes([255])
    assert unpack(fields, payload) == (40, 70, 255)
    assert transform_output(1, 0) == -249.5
    # Transforms 7 and 8 are defined and unused by every field row.
    assert transform_output(7, 10) == 0.0031746 * 10
    assert transform_output(8, 0) == -4.1086


def test_null_seq_sorts_before_zero_and_names_fold_case() -> None:
    fields = (
        Field("B", 2),
        Field("a", 2),
        Field("_z", 2),
        Field("c", 2, seq=0),
    )
    assert [field.name for field in sort_fields(fields)] == ["_z", "a", "B", "c"]
    assert [field.name for field in sorted(fields, key=lambda field: field.name)] == [
        "B",
        "_z",
        "a",
        "c",
    ]
    assert _sort_tree(irig106_fields()) == irig106_fields()


def test_real_tree_packet_nodes_cover_the_codec_census() -> None:
    """Configurator packet nodes in the hardware extract name every codec packet."""
    boards = Path(__file__).resolve().parent / "fixtures" / "hardware" / "real_boards.json"
    loaded = json.loads(boards.read_text(encoding="utf-8"))
    nodes = loaded["treeversions"]
    names = {row["name"] for row in nodes if row["iconid"] in (6, 7)}
    census = {name for _, name, _, _, _, _ in _PACKET_SIZES}
    assert census <= names


def test_legacy_opc_name_and_port_match_the_server_row() -> None:
    assert LEGACY_OPC_DA_SERVER == "National Instruments.Variable Engine.1"
    assert DEFAULT_BRIDGE_PORT == 2357
    assert DEFAULT_STAGE_COUNT == 2


def _expand(layout: list[dict[str, object]], values: dict[str, object]) -> list[Value]:
    expanded: list[Value] = []
    for entry in layout:
        name = str(entry["name"])
        qty = int(str(entry["qty"]))
        if name in values:
            raw = values[name]
            if qty == 1:
                expanded.append(_as_value(raw))
            else:
                assert isinstance(raw, list)
                assert len(raw) == qty
                expanded.extend(_as_value(item) for item in raw)
        else:
            expanded.extend([0] * qty)
    return expanded


def _as_value(item: object) -> Value:
    if item is None or isinstance(item, (bool, int, float)):
        return item
    raise AssertionError(type(item).__name__)


def _bit_offsets(layout: list[FlatField]) -> dict[str, int]:
    offsets: dict[str, int] = {}
    bit = 0
    for item in layout:
        offsets[item.name] = bit
        bit += item.bit_width
    assert bit == IRIG106_BITS
    return offsets


def _primitive_leaves(fields: tuple[Field, ...]) -> int:
    count = 0
    for field in fields:
        if field.fields:
            count += _primitive_leaves(field.fields)
        else:
            count += 1
    return count


def _sort_tree(fields: tuple[Field, ...]) -> tuple[Field, ...]:
    return tuple(replace(field, fields=_sort_tree(field.fields)) for field in sort_fields(fields))
