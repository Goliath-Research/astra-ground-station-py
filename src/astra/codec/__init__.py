"""Field layout, bit pack/unpack, and transforms.

Phase 1 of the migration. ``pack`` and ``unpack`` are not implemented.
The wire format is the little-endian bit packer in ``AstraVarPacket.pas``,
not a length-prefixed blob.
"""

from collections.abc import Sequence


def pack(values: Sequence[object]) -> bytes:
    """Pack field values into a payload.

    Raises:
        NotImplementedError: always, until phase 1.
    """
    del values
    raise NotImplementedError("codec pack is not ported")


def unpack(payload: bytes) -> tuple[object, ...]:
    """Unpack a payload into field values.

    Raises:
        NotImplementedError: always, until phase 1.
    """
    del payload
    raise NotImplementedError("codec unpack is not ported")
