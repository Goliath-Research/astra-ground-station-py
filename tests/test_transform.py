"""TransformOutput samples and the OPC SyncWrite substitution.

The six samples are the ones transcribed from astra-ground-station PR #6.
``opc_substituted`` is false for every sample. ``pack`` does not apply either
step.
"""

import struct

import pytest

from astra.codec import (
    CodecError,
    Field,
    get_opc_type,
    pack,
    substitute_opc_zero,
    sync_write,
    transform_output,
)

_SAMPLES = (
    (1, 1000.0, -13.77000000000001, "10d7a3703d8a2bc0"),
    (1, 0.0, -249.5, "0000000000306fc0"),
    (2, 1000.0, 13.810000000000002, "2085eb51b89e2b40"),
    (10, 1023.0, 100.0, "0000000000005940"),
    (11, 5.0, 5.0, "0000000000001440"),
    (14, 2500.0, 2.5, "0000000000000440"),
)


@pytest.mark.parametrize(("transform_id", "x", "y", "hex_le"), _SAMPLES)
def test_transform_sample(transform_id: int, x: float, y: float, hex_le: str) -> None:
    result = transform_output(transform_id, x)
    assert isinstance(result, float)
    assert result == y
    assert struct.pack("<d", result).hex() == hex_le
    published = sync_write(x, type_id=8, transform_id=transform_id)
    assert published == result


def test_other_transform_ids_return_the_value() -> None:
    assert transform_output(0, 3) == 3
    assert transform_output(15, -2.5) == -2.5
    assert transform_output(99, 1) == 1


def test_non_numeric_values_raise() -> None:
    with pytest.raises(CodecError):
        transform_output(1, "nope")  # type: ignore[arg-type]
    with pytest.raises(CodecError):
        transform_output(1, None)
    with pytest.raises(CodecError):
        pack((Field("a", 2),), ["x"])  # type: ignore[list-item]


def test_syncwrite_substitutes_scalar_zero_only() -> None:
    assert get_opc_type(9) == "Single"
    assert get_opc_type(10) == "Double"
    assert get_opc_type(2) == "UInt8"
    assert get_opc_type(2, qty=3) == "Array of UInt8"
    assert get_opc_type(2, transform_id=11) == "Double"
    assert get_opc_type(9, qty=2, transform_id=1) == "Array of Double"
    assert sync_write(0.0, type_id=9) == 1e-7
    assert sync_write(-0.0, type_id=10) == 1e-7
    assert sync_write(0, type_id=2, transform_id=11) == 1e-7
    assert sync_write(0, type_id=2) == 0
    assert sync_write([0.0, 0.0], type_id=9, qty=2) == (0.0, 0.0)
    nan = sync_write(float("nan"), type_id=9)
    assert isinstance(nan, float) and nan != nan
    assert pack((Field("x", 10),), [0.0]) == b"\x00" * 8
    assert substitute_opc_zero(0.0) == 1e-7
    assert substitute_opc_zero(1.25) == 1.25
