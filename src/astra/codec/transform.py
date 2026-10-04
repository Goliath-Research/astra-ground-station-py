"""Output transforms and the OPC zero substitution.

``TransformInput`` is never called. ``TransformOutput`` runs on the way to
OPC. Its polynomials are in ``AstraVarPacket.pas``. ``CODEC_SPEC.md`` from
astra-ground-station PR #6, which cites those formulas, was not on disk, so
``transform_output`` does not invent them.

The replacement of ``0`` with ``1e-7`` is ``AstraInpPopper.SyncWrite`` for an
OPC Single or Double. ``pack`` does not call it, and the substitution is not
on the wire.
"""

from astra.codec.errors import CodecError

OPC_ZERO_SUBSTITUTE = 1e-7


def substitute_opc_zero(value: float) -> float:
    """Return the value ``AstraInpPopper.SyncWrite`` would write.

    A Single or Double that compares equal to zero, including ``-0.0``,
    becomes ``1e-7``. Any other number is unchanged. This is not a wire
    transform.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CodecError(f"OPC value must be a float, got {type(value).__name__}")
    if value == 0.0:
        return OPC_ZERO_SUBSTITUTE
    return float(value)


def transform_output(transform_id: int, value: float) -> float:
    """Apply ``TransformOutput`` id ``transform_id`` to ``value``.

    Raises:
        CodecError: ``transform_id`` is outside 1..14, or ``value`` is not a
            real number.
        NotImplementedError: the id is in range. The polynomials were not in
            the files available to this port.
    """
    if isinstance(transform_id, bool) or not isinstance(transform_id, int):
        raise CodecError(f"unknown TransformOutput id {transform_id!r}")
    if transform_id < 1 or transform_id > 14:
        raise CodecError(f"unknown TransformOutput id {transform_id}")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CodecError(f"transform input must be a float, got {type(value).__name__}")
    raise NotImplementedError(
        "TransformOutput formulas are in AstraVarPacket.pas. "
        "CODEC_SPEC.md from astra-ground-station PR #6 was not on disk, "
        "so the polynomials were not ported."
    )
