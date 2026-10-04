"""Vehicle data types and the flat layout a later Mojo packer would take.

Type ids and bit widths are ``TVehicleDataTypes`` in ``AstraVarPacket.pas``.
Override bits are one bool each, appended after the whole flattened record.
An array field contributes one override bit, not one per element. A nested
record (type id > 100) is flattened in field order, and each element's own
override bits stay at the end of that element. Arrays are packed back to
back. Nested records and arrays are not padded to a byte boundary.

Field names do not change the payload. ``CODEC_SPEC.md`` from
astra-ground-station PR #6 was not on disk, so these comments do not cite
Delphi line numbers.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from astra.codec.errors import CodecError

# Id, name, bits. Q types use the same widths; scaling is not applied here.
TYPE_WIDTH: dict[int, int] = {
    1: 1,  # bool
    2: 8,  # u8
    3: 12,  # u12
    4: 16,  # u16
    5: 32,  # u32
    6: 8,  # i8
    7: 16,  # i16
    8: 32,  # i32
    9: 32,  # f32
    10: 64,  # f64
    11: 32,  # i32q8
    12: 32,  # i32q16
    13: 8,  # u8q8
    14: 16,  # u16q16
}

SIGNED_TYPE_IDS = frozenset({6, 7, 8, 11, 12})
FLOAT_TYPE_IDS = frozenset({9, 10})
TYPE_NAMES: dict[int, str] = {
    1: "bool",
    2: "u8",
    3: "u12",
    4: "u16",
    5: "u32",
    6: "i8",
    7: "i16",
    8: "i32",
    9: "f32",
    10: "f64",
    11: "i32q8",
    12: "i32q16",
    13: "u8q8",
    14: "u16q16",
}

FlatRole = Literal["value", "override"]


@dataclass(frozen=True, slots=True)
class Field:
    """One configurator field, possibly a nested record (``type_id > 100``)."""

    name: str
    type_id: int
    qty: int = 1
    override: bool = False
    fields: tuple[Field, ...] = ()


@dataclass(frozen=True, slots=True)
class FlatField:
    """One scalar in wire order.

    ``kind`` is a ``TVehicleDataTypes`` id. An ``ovr_`` bit is kind 1 and
    width 1, the same shape as a bool. ``(bit_width, kind)`` is the pair a
    later ``pack_records`` implementation would receive.
    """

    name: str
    kind: int
    bit_width: int
    role: FlatRole = "value"

    @property
    def mojo_pair(self) -> tuple[int, int]:
        """Return ``(bit_width, kind)``."""
        return (self.bit_width, self.kind)


def flatten(fields: Sequence[Field]) -> tuple[FlatField, ...]:
    """Return scalars in the order ``SaveValue`` then ``LoadFieldOvrs`` use.

    Inside one record the value bits come first, including each nested
    record's own trailing override bits, repeated once per array element.
    This record's ``ovr_`` bits are one bool each, appended after that whole
    record. An array gets one of those bits, not one per element.
    """
    values: list[FlatField] = []
    overrides: list[FlatField] = []
    for field in fields:
        _append_field(field, "", values, overrides)
    return tuple([*values, *overrides])


def encoded_bit_count(fields: Sequence[Field]) -> int:
    """Return the number of payload bits, before the final byte pad."""
    return sum(item.bit_width for item in flatten(fields))


def encoded_size(fields: Sequence[Field]) -> int:
    """Return the payload size in bytes.

    Matches ``spcalcvartypesizes``: ``ceiling(bit_count / 8)`` once, at this
    layout. Nested records are not padded to a byte on their own.
    """
    bits = encoded_bit_count(fields)
    return (bits + 7) // 8


def _append_field(
    field: Field,
    prefix: str,
    values: list[FlatField],
    overrides: list[FlatField],
) -> None:
    _check_field(field)
    base = field.name if prefix == "" else f"{prefix}_{field.name}"
    if field.fields:
        for index in range(field.qty):
            element = base if field.qty == 1 else f"{base}_{index}"
            child_values: list[FlatField] = []
            child_overrides: list[FlatField] = []
            for child in field.fields:
                _append_field(child, element, child_values, child_overrides)
            values.extend(child_values)
            values.extend(child_overrides)
        if field.override:
            overrides.append(FlatField(f"ovr_{base}", 1, 1, "override"))
        return
    width = TYPE_WIDTH[field.type_id]
    for index in range(field.qty):
        name = base if field.qty == 1 else f"{base}_{index}"
        values.append(FlatField(name, field.type_id, width, "value"))
    if field.override:
        overrides.append(FlatField(f"ovr_{base}", 1, 1, "override"))


def _check_field(field: Field) -> None:
    if not isinstance(field.name, str) or field.name == "":
        raise CodecError("field name must be a non-empty string")
    if isinstance(field.qty, bool) or not isinstance(field.qty, int) or field.qty < 1:
        raise CodecError(f"{field.name}: qty must be an integer >= 1")
    if not isinstance(field.override, bool):
        raise CodecError(f"{field.name}: override must be a bool")
    nested = len(field.fields) > 0
    if nested:
        if field.type_id <= 100:
            raise CodecError(f"{field.name}: a nested record needs type_id > 100")
        return
    if field.type_id not in TYPE_WIDTH:
        raise CodecError(f"{field.name}: unknown type id {field.type_id}")
