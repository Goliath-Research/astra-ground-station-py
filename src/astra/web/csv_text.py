"""CSV text in the shape of ``ExportDataSetToCSV``.

The Delphi writer uses ``;`` as the delimiter and ``"`` as the quote. A cell
is quoted when it contains a space, the delimiter, or a quote. Quotes inside
a cell are doubled. Booleans are ``0`` and ``1``. Lines end with CR LF, which
is what ``TStreamWriter`` writes on Windows.
"""

from __future__ import annotations

from typing import Any

_BOOLEAN = frozenset({"override", "insequence"})


def csv_document(header: tuple[str, ...], rows: list[dict[str, Any]]) -> str:
    """Return one CSV document, including the trailing line break."""
    lines = [";".join(header)]
    for row in rows:
        lines.append(";".join(_cell(row[name], boolean=name in _BOOLEAN) for name in header))
    return "\r\n".join(lines) + "\r\n"


def _cell(value: Any, *, boolean: bool) -> str:
    if value is None:
        return ""
    if boolean or isinstance(value, bool):
        return "1" if value else "0"
    text = str(value)
    if any(char <= " " or char in {";", '"'} for char in text):
        return '"' + text.replace('"', '""') + '"'
    return text
