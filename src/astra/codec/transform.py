"""``TransformOutput`` and the OPC zero substitution.

``AstraVarPacket.pas`` ``TransformOutput`` (1130-1156) runs on the way to
OPC, in binary64, and is not part of ``SavePacket``. ``TransformInput``
(1102-1128) is never called. ``AstraInpPopper.SyncWrite`` (95-120) applies
the transform and then, for an OPC type of exactly ``Single`` or ``Double``,
replaces a value that compares equal to zero with ``1e-7`` (100-116). NaN
is left alone. The result is not written back into the packet.

``GetOpcType`` (1188-1197) returns ``Double`` when ``TransformationID > 0``,
otherwise the type's OPC name, and ``Array of ...`` when ``Qty > 1``.
"""

from collections.abc import Callable, Sequence

from astra.codec.errors import CodecError
from astra.codec.python_pack import Value

OPC_ZERO_SUBSTITUTE = 1e-7

# OPC names from TVehicleDataTypes, as recorded in docs/MIGRATION.md.
_OPC_NAMES: dict[int, str] = {
    1: "Boolean",
    2: "UInt8",
    3: "UInt16",
    4: "UInt16",
    5: "UInt32",
    6: "Int8",
    7: "Int16",
    8: "Int32",
    9: "Single",
    10: "Double",
    11: "Int32",
    12: "Int32",
    13: "UInt8",
    14: "UInt16",
}

_Output = Callable[[float], float]

# Horner form for id 1 is the expression in the spec, not a rearranged polynomial.
_OUTPUT: dict[int, _Output] = {
    1: lambda x: -249.5 + x * (0.1987 + x * (-7.47e-6 + 4.45e-8 * x)),
    2: lambda x: -62.5 + 0.07631 * x,
    3: lambda x: -250 + 0.3053 * x,
    4: lambda x: -2500 + 3.053 * x,
    5: lambda x: 0.008057 * x,
    6: lambda x: 0.007727 * x,
    7: lambda x: 0.0031746 * x,
    8: lambda x: -4.1086 + 0.00498 * x,
    9: lambda x: 0.1 * x,
    10: lambda x: 100 * x / 1023,
    11: lambda x: x,
    12: lambda x: 0.1 * x,
    13: lambda x: 10 * x,
    14: lambda x: 0.001 * x,
}


def get_opc_type(type_id: int, qty: int = 1, transform_id: int = 0) -> str:
    """Return the OPC type name ``GetOpcType`` would publish."""
    _require_id("type_id", type_id)
    _require_id("qty", qty, minimum=1)
    if isinstance(transform_id, bool) or not isinstance(transform_id, int):
        raise CodecError(f"transform_id must be an integer, got {transform_id!r}")
    if type_id not in _OPC_NAMES:
        raise CodecError(f"unknown type id {type_id}")
    base = "Double" if transform_id > 0 else _OPC_NAMES[type_id]
    if qty > 1:
        return f"Array of {base}"
    return base


def transform_output(transform_id: int, value: Value) -> Value:
    """Apply ``TransformOutput`` id ``transform_id``.

    Ids 1-14 use the polynomials above. Any other id returns ``value``.
    A non-numeric value, including ``bool`` and ``None``, raises
    ``CodecError``.
    """
    number = _number(value)
    if isinstance(transform_id, bool) or not isinstance(transform_id, int):
        raise CodecError(f"transform_id must be an integer, got {transform_id!r}")
    formula = _OUTPUT.get(transform_id)
    if formula is None:
        return number
    return formula(float(number))


def substitute_opc_zero(value: float) -> float:
    """Return ``1e-7`` when ``value`` compares equal to zero.

    This is the comparison inside ``SyncWrite``. It does not decide whether
    the OPC type is eligible. ``-0.0`` compares equal to zero. NaN does not.
    """
    number = _number(value)
    if number == 0.0:
        return OPC_ZERO_SUBSTITUTE
    return float(number)


def sync_write(
    value: object, *, type_id: int, qty: int = 1, transform_id: int = 0
) -> Value | tuple[Value, ...]:
    """Return the value ``SyncWrite`` would publish.

    ``TransformOutput`` runs first. The ``1e-7`` substitution then applies
    only when the OPC type is exactly ``Single`` or ``Double`` and the
    transformed value compares equal to zero. Arrays are transformed per
    element and are never substituted. The packet buffer is not modified.
    """
    opc_type = get_opc_type(type_id, qty, transform_id)
    if qty > 1:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise CodecError("an array OPC value must be a sequence")
        if len(value) != qty:
            raise CodecError(f"expected {qty} OPC elements, got {len(value)}")
        published: list[Value] = []
        for item in value:
            published.append(transform_output(transform_id, item))
        return tuple(published)
    transformed = transform_output(transform_id, value)  # type: ignore[arg-type]
    if opc_type in {"Single", "Double"} and transformed == 0.0:
        return OPC_ZERO_SUBSTITUTE
    return transformed


def _number(value: object) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CodecError(f"expected a number, got {type(value).__name__}")
    return value


def _require_id(name: str, value: int, *, minimum: int = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CodecError(f"{name} must be an integer >= {minimum}, got {value!r}")
