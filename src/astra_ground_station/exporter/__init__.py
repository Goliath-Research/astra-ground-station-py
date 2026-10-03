"""Export library. Serialization of real rows is not ported."""

from collections.abc import Mapping, Sequence

EXPORT_HEADER = b"ASTRA_EXPORT_PLACEHOLDER\n"


def export_rows(rows: Sequence[Mapping[str, object]]) -> bytes:
    """Return a placeholder payload.

    Row contents are ignored on purpose so a caller cannot mistake this for
    a real export.
    """
    del rows
    return EXPORT_HEADER
