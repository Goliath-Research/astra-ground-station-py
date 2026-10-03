"""``.DAT`` reader and writer.

The on-disk layout is fixed by ``TAstraBinLogFile``: magic ``0x1A2B``, check
``0xE5C4``, a 20-byte little-endian header, then records of an OLE
``TDateTime`` plus the payload. Reading and writing are phase 1.
"""

import struct
from datetime import date

MAGIC = 0x1A2B
CHECK = 0xE5C4
# word, word, integer, integer, integer, integer. No padding at Delphi's default alignment.
HEADER = struct.Struct("<HHIIII")
# Header plus the 8-byte OLE timestamp that starts each record.
HEADER_AND_TIMESTAMP = struct.Struct("<HHIIIId")
OLE_EPOCH = date(1899, 12, 30)


def dat_filename(test_id: int, interface_id: int) -> str:
    """Return ``LOG-T{test}-I{intf}.DAT``."""
    return f"LOG-T{test_id}-I{interface_id}.DAT"


def read_dat(path: str) -> None:
    """Read a binary log.

    Raises:
        NotImplementedError: always, until phase 1.
    """
    del path
    raise NotImplementedError("binary log reader is not ported")
