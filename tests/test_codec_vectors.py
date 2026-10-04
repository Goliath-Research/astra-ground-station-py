"""The 29 golden vectors transcribed from astra-ground-station PR #6.

Each vector keeps its id, layout, values, bit length, expected hex, and
provenance. ``tests/data/codec_vectors.json`` is that transcription.
``u8_out_of_range_wraps`` is the one vector whose expected hex is the
legacy low-bit wrap. Default ``pack`` clips that input instead.
"""

import json
import struct
from pathlib import Path

import pytest

from astra.codec import Field, device_t_ms, pack, pack_id_payload, unpack
from astra.codec.types import TYPE_WIDTH, encoded_bit_count

_PATH = Path(__file__).parent / "data" / "codec_vectors.json"
_DOCUMENT = json.loads(_PATH.read_text(encoding="utf-8"))
_VECTORS = _DOCUMENT["vectors"]


def _field(node: dict[str, object]) -> Field:
    raw_children = node.get("fields", ())
    children: tuple[Field, ...] = ()
    if isinstance(raw_children, list):
        children = tuple(_field(child) for child in raw_children)
    if children:
        type_id = node["type_id"]
        assert isinstance(type_id, int)
        return Field(
            str(node["name"]),
            type_id,
            qty=_int(node.get("qty", 1)),
            override=bool(node.get("override", False)),
            fields=children,
        )
    type_id = node["type_id"]
    bits = node["bits"]
    assert isinstance(type_id, int)
    assert isinstance(bits, int)
    assert TYPE_WIDTH[type_id] == bits
    return Field(
        str(node["name"]),
        type_id,
        qty=_int(node.get("qty", 1)),
        override=bool(node.get("override", False)),
    )


def _int(value: object) -> int:
    assert isinstance(value, int) and not isinstance(value, bool)
    return value


def _values(raw: list[object]) -> list[object]:
    decoded: list[object] = []
    for item in raw:
        if isinstance(item, dict):
            bits = str(item["nan_bits"])
            width = _int(item["width"])
            word = int(bits, 16).to_bytes(width // 8, "little")
            fmt = "<f" if width == 32 else "<d"
            decoded.append(struct.unpack(fmt, word)[0])
        else:
            decoded.append(item)
    return decoded


def _ids() -> list[str]:
    return [str(vector["id"]) for vector in _VECTORS]


@pytest.mark.parametrize("vector_id", _ids())
def test_codec_vector(vector_id: str) -> None:
    vector = next(item for item in _VECTORS if item["id"] == vector_id)
    fields_raw = vector["fields"]
    values_raw = vector["values"]
    assert isinstance(fields_raw, list)
    assert isinstance(values_raw, list)
    fields = tuple(_field(node) for node in fields_raw)
    values = _values(values_raw)
    assert encoded_bit_count(fields) == vector["bit_length"]
    payload = pack(fields, values)  # type: ignore[arg-type]
    if vector_id == "u8_out_of_range_wraps":
        # The transcribed hex is Delphi low-bit wrap (300 -> 2c). Default pack clips to 255.
        assert payload.hex() == "ff"
        assert unpack(fields, payload) == (255,)
        wrapped = pack(fields, values, overflow="wrap")  # type: ignore[arg-type]
        assert wrapped.hex() == vector["expected_hex"]
        assert unpack(fields, wrapped) == (0x2C,)
        return
    if "payload_hex" in vector:
        assert payload.hex() == vector["payload_hex"]
        assert device_t_ms(payload) == vector["device_t_ms"]
        packet_id = vector["packet_id"]
        assert isinstance(packet_id, int)
        assert pack_id_payload(packet_id, payload).hex() == vector["expected_hex"]
    else:
        assert payload.hex() == vector["expected_hex"]
    if any(item is None or isinstance(item, dict) for item in values_raw):
        return
    restored = unpack(fields, payload)
    assert pack(fields, list(restored)) == payload
    assert restored == tuple(values)


def test_vector_file_has_the_transcribed_set() -> None:
    assert _DOCUMENT["note"].startswith("Transcribed from astra-ground-station")
    assert _ids() == [
        "bool_false",
        "bool_true",
        "u8",
        "u12",
        "u16",
        "u32",
        "i8",
        "i16",
        "i32",
        "f32",
        "f64",
        "i32q8_raw",
        "i32q16_raw",
        "u8q8_raw",
        "u16q16_raw",
        "u12_after_bool",
        "u16_after_four_bools",
        "override_after_record",
        "override_two_fields",
        "array_u8",
        "array_u12_with_one_override",
        "nested_record",
        "array_of_records",
        "null_becomes_zero",
        "u8_out_of_range_wraps",
        "f32_nan",
        "udp_frame",
        "minor_frame_1_of_2",
        "minor_frame_2_of_2",
    ]
