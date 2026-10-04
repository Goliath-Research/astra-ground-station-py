"""Field layout and the pure-Python bit packer.

``pack`` / ``unpack`` follow ``TVehicleDataType.SaveValue`` and ``LoadValue``
over ``TBitStream``. Out-of-range integers keep their low bits, and null
packs as 0. Mojo is not imported. ``ASTRA_NATIVE_BACKEND=mojo`` is rejected
until ``pack_records`` exists; the flat ``(bit_width, kind)`` layout is the
surface that function would take. ``transform_output`` raises: the
polynomials were not in the files available here. ``substitute_opc_zero``
is the OPC ``SyncWrite`` helper and is not applied by ``pack``.
"""

from collections.abc import Sequence

from astra.codec.errors import CodecError
from astra.codec.framing import device_t_ms, pack_id_payload, unpack_id_payload
from astra.codec.python_pack import Value, pack_flat, pack_unsigned_bits, unpack_flat
from astra.codec.transform import substitute_opc_zero, transform_output
from astra.codec.types import (
    TYPE_NAMES,
    TYPE_WIDTH,
    Field,
    FlatField,
    encoded_size,
    flatten,
)
from astra.native import active_backend

__all__ = [
    "TYPE_NAMES",
    "TYPE_WIDTH",
    "CodecError",
    "Field",
    "FlatField",
    "Value",
    "device_t_ms",
    "encoded_size",
    "flatten",
    "pack",
    "pack_flat",
    "pack_id_payload",
    "pack_unsigned_bits",
    "substitute_opc_zero",
    "transform_output",
    "unpack",
    "unpack_flat",
    "unpack_id_payload",
]


def pack(fields: Sequence[Field], values: Sequence[Value]) -> bytes:
    """Pack ``values`` for ``fields`` into a payload.

    The buffer is cleared first. Unused bits in the last byte stay zero.
    """
    active_backend()
    return pack_flat(flatten(fields), values)


def unpack(fields: Sequence[Field], payload: bytes) -> tuple[Value, ...]:
    """Unpack ``payload`` into one value per flattened scalar."""
    active_backend()
    return unpack_flat(flatten(fields), payload)
