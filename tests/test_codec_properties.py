"""Round-trip properties of the integer-shift packer.

These do not call Delphi. They check that ``pack_flat`` matches a separate
bit-at-a-time loop for random in-range values, including a leading run of
bools so a later ``f64`` starts off a byte boundary.
"""

import struct

from hypothesis import given, settings
from hypothesis import strategies as st

from astra.codec import Field, encoded_size, flatten, pack, pack_flat, unpack
from astra.codec.types import FLOAT_TYPE_IDS, SIGNED_TYPE_IDS, TYPE_WIDTH, encoded_bit_count
from tests.savebit_reference import save_bits

Value = bool | int | float


def _values_for(kind: int) -> st.SearchStrategy[Value]:
    width = TYPE_WIDTH[kind]
    if kind == 1:
        return st.booleans()
    if kind == 9:
        return st.floats(allow_nan=False, allow_infinity=False, width=32)
    if kind == 10:
        return st.floats(allow_nan=False, allow_infinity=False, width=64)
    if kind in SIGNED_TYPE_IDS:
        limit = 1 << (width - 1)
        return st.integers(min_value=-limit, max_value=limit - 1)
    return st.integers(min_value=0, max_value=(1 << width) - 1)


def _field_and_values() -> st.SearchStrategy[tuple[Field, list[Value]]]:
    return st.integers(min_value=1, max_value=14).flatmap(
        lambda kind: st.tuples(
            st.just(kind),
            st.booleans(),
            st.lists(_values_for(kind), min_size=1, max_size=3),
        ).map(_named_field)
    )


def _named_field(parts: tuple[int, bool, list[Value]]) -> tuple[Field, list[Value]]:
    kind, override, samples = parts
    return Field("v", kind, qty=len(samples), override=override), samples


def _bit_pattern(kind: int, width: int, value: Value) -> int:
    if kind in FLOAT_TYPE_IDS:
        fmt = "<f" if kind == 9 else "<d"
        return int.from_bytes(struct.pack(fmt, float(value)), "little")
    if isinstance(value, bool):
        return 1 if value else 0
    return int(value) & ((1 << width) - 1)


def _padding_is_clear(payload: bytes, fields: tuple[Field, ...]) -> None:
    assert len(payload) == encoded_size(fields)
    spare = encoded_size(fields) * 8 - encoded_bit_count(fields)
    if spare == 0:
        return
    unused = (0xFF << (8 - spare)) & 0xFF
    assert payload[-1] & unused == 0


@settings(deadline=None, derandomize=True, max_examples=40)
@given(st.lists(_field_and_values(), min_size=1, max_size=6))
def test_shift_packer_matches_savebit_and_round_trips(
    generated: list[tuple[Field, list[Value]]],
) -> None:
    fields = tuple(
        Field(f"f{index}", item.type_id, qty=item.qty, override=item.override)
        for index, (item, _values) in enumerate(generated)
    )
    values: list[Value] = [value for _field, samples in generated for value in samples]
    values.extend(True for item, _samples in generated if item.override)
    layout = flatten(fields)
    payload = pack(fields, values)
    assert payload == pack_flat(layout, values)
    parts = [
        (item.bit_width, _bit_pattern(item.kind, item.bit_width, value))
        for item, value in zip(layout, values, strict=True)
    ]
    assert save_bits(parts) == payload
    assert pack(fields, unpack(fields, payload)) == payload
    _padding_is_clear(payload, fields)
    for item, original, restored in zip(layout, values, unpack(fields, payload), strict=True):
        if item.kind not in FLOAT_TYPE_IDS and item.role == "value":
            assert restored == original


@settings(deadline=None, derandomize=True, max_examples=25)
@given(
    st.integers(min_value=1, max_value=12),
    st.floats(allow_nan=False, allow_infinity=False, width=64),
    st.integers(min_value=0, max_value=0xFFF),
)
def test_f64_after_a_bit_run_round_trips(leading_bools: int, number: float, sample: int) -> None:
    fields = tuple(Field(f"b{index}", 1) for index in range(leading_bools)) + (
        Field("sample", 3),
        Field("x", 10),
    )
    values: list[Value] = [True] * leading_bools
    values.extend([sample, number])
    payload = pack(fields, values)
    restored = unpack(fields, payload)
    assert restored[: leading_bools + 1] == tuple(values[: leading_bools + 1])
    assert pack(fields, restored) == payload
    _padding_is_clear(payload, fields)
