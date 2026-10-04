"""``.DAT`` reader and writer.

The on-disk layout is fixed by ``TAstraBinLogFile``: magic ``0x1A2B``, check
``0xE5C4``, version 1, test id, interface id, record size, then records of an
OLE ``TDateTime`` plus ``RecSize`` payload bytes. The timestamp is naive
local time. The payload is the datagram body, without the packet id.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

MAGIC = 0x1A2B
CHECK = 0xE5C4
VERSION = 1
# word, word, integer, integer, integer, integer. No padding at Delphi's default alignment.
HEADER = struct.Struct("<HHIIII")
# Header plus the 8-byte OLE timestamp that starts each record.
HEADER_AND_TIMESTAMP = struct.Struct("<HHIIIId")
OLE_EPOCH = date(1899, 12, 30)
_OLE_EPOCH_DT = datetime(1899, 12, 30)
_DAY_SECONDS = 86400.0
_STAMP = struct.Struct("<d")


@dataclass(frozen=True, slots=True)
class LogRecord:
    """One stored payload and the OLE day-count written beside it."""

    ole_time: float
    payload: bytes


@dataclass(frozen=True, slots=True)
class BinLog:
    """A binary log header plus its records."""

    version: int
    test_id: int
    interface_id: int
    rec_size: int
    records: tuple[LogRecord, ...]


def dat_filename(test_id: int, interface_id: int) -> str:
    """Return ``LOG-T{test}-I{intf}.DAT``."""
    return f"LOG-T{test_id}-I{interface_id}.DAT"


def ole_days(moment: datetime) -> float:
    """Return a naive local ``datetime`` as an OLE day count."""
    if moment.tzinfo is not None:
        raise ValueError("timestamp must be naive local time")
    return (moment - _OLE_EPOCH_DT).total_seconds() / _DAY_SECONDS


def header_bytes(test_id: int, interface_id: int, rec_size: int) -> bytes:
    """Return the 20-byte log header."""
    _check_id("test id", test_id)
    _check_id("interface id", interface_id)
    _check_rec_size(rec_size)
    return HEADER.pack(MAGIC, CHECK, VERSION, test_id, interface_id, rec_size)


def record_bytes(ole_time: float, payload: bytes, rec_size: int) -> bytes:
    """Return one timestamp plus a payload of ``rec_size`` bytes."""
    if not _finite(ole_time):
        raise ValueError("timestamp is not a finite float")
    if not isinstance(payload, bytes) or len(payload) != rec_size:
        raise ValueError("payload length does not match the record size")
    return _STAMP.pack(ole_time) + payload


def write_dat(
    path: str | Path,
    *,
    test_id: int,
    interface_id: int,
    payloads: Sequence[bytes],
    stamped_at: datetime,
) -> None:
    """Write a log whose every record uses ``stamped_at``."""
    if not payloads:
        raise ValueError("a log needs at least one payload")
    rec_size = len(payloads[0])
    ole_time = ole_days(stamped_at)
    body = bytearray(header_bytes(test_id, interface_id, rec_size))
    for payload in payloads:
        body.extend(record_bytes(ole_time, payload, rec_size))
    Path(path).write_bytes(body)


def read_dat(path: str | Path) -> BinLog:
    """Read a binary log. A short or mismatched file is rejected."""
    data = Path(path).read_bytes()
    if len(data) < HEADER.size:
        raise ValueError("not a binary log")
    magic, check, version, test_id, interface_id, rec_size = HEADER.unpack_from(data)
    if magic != MAGIC or check != CHECK or version != VERSION:
        raise ValueError("not a binary log")
    if rec_size < 0:
        raise ValueError("not a binary log")
    stride = _STAMP.size + rec_size
    rest = data[HEADER.size :]
    if len(rest) % stride != 0:
        raise ValueError("not a binary log")
    records: list[LogRecord] = []
    offset = HEADER.size
    while offset < len(data):
        (ole_time,) = _STAMP.unpack_from(data, offset)
        start = offset + _STAMP.size
        payload = bytes(data[start : start + rec_size])
        records.append(LogRecord(ole_time=ole_time, payload=payload))
        offset = start + rec_size
    return BinLog(
        version=version,
        test_id=test_id,
        interface_id=interface_id,
        rec_size=rec_size,
        records=tuple(records),
    )


def _finite(value: float) -> bool:
    if not isinstance(value, float):
        return False
    return value == value and value != float("inf") and value != float("-inf")


def _check_id(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} does not fit in a signed 32-bit integer")
    if value < -0x80000000 or value > 0x7FFFFFFF:
        raise ValueError(f"{name} does not fit in a signed 32-bit integer")


def _check_rec_size(rec_size: int) -> None:
    if isinstance(rec_size, bool) or not isinstance(rec_size, int):
        raise ValueError("record size must be from 4 to 65503")
    if rec_size < 4 or rec_size > 65503:
        raise ValueError("record size must be from 4 to 65503")
