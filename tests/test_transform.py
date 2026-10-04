"""OPC zero substitution and the unported TransformOutput polynomials.

``CODEC_SPEC.md`` from astra-ground-station PR #6 was not on disk, so the
formulas in ``AstraVarPacket.pas`` ``TransformOutput`` were not loaded.
``AstraInpPopper.SyncWrite`` is the only place ``0`` becomes ``1e-7``.
"""

import pytest

from astra.codec import CodecError, Field, pack, substitute_opc_zero, transform_output


def test_syncwrite_replaces_only_a_zero() -> None:
    assert substitute_opc_zero(0.0) == 1e-7
    assert substitute_opc_zero(-0.0) == 1e-7
    assert substitute_opc_zero(1.0) == 1.0
    assert substitute_opc_zero(-1.5) == -1.5


def test_pack_does_not_apply_the_opc_substitution() -> None:
    assert pack((Field("x", 9),), [0.0]) == b"\x00\x00\x00\x00"
    assert pack((Field("x", 10),), [0.0]) == b"\x00" * 8


def test_transform_output_is_not_ported() -> None:
    with pytest.raises(NotImplementedError, match="CODEC_SPEC.md"):
        transform_output(1, 0.0)
    with pytest.raises(NotImplementedError, match="AstraVarPacket"):
        transform_output(14, 1.0)


def test_unknown_transform_ids_are_rejected() -> None:
    with pytest.raises(CodecError):
        transform_output(0, 1.0)
    with pytest.raises(CodecError):
        transform_output(15, 1.0)
