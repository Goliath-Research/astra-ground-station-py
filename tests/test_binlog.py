import struct
from datetime import datetime
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from astra.binlog import (
    CHECK,
    HEADER,
    MAGIC,
    OLE_EPOCH,
    dat_filename,
    ole_days,
    read_dat,
    write_dat,
)


def test_header_layout_matches_the_delphi_record() -> None:
    assert MAGIC == 0x1A2B
    assert CHECK == 0xE5C4
    assert HEADER.size == 20
    assert struct.calcsize("<HHIIII") == 20
    assert OLE_EPOCH.isoformat() == "1899-12-30"


@settings(deadline=None, derandomize=True)
@given(
    st.integers(min_value=0, max_value=1_000_000),
    st.integers(min_value=0, max_value=1_000_000),
)
def test_dat_filename(test_id: int, interface_id: int) -> None:
    assert dat_filename(test_id, interface_id) == f"LOG-T{test_id}-I{interface_id}.DAT"


def test_dat_round_trip(tmp_path: Path) -> None:
    moment = datetime(2026, 1, 2, 3, 4, 5)
    first = struct.pack("<i", 100) + b"\x01\x02\x03\x04"
    second = struct.pack("<i", 200) + b"\x05\x06\x07\x08"
    path = tmp_path / "LOG-T7-I4.DAT"
    write_dat(path, test_id=7, interface_id=4, payloads=(first, second), stamped_at=moment)
    log = read_dat(path)
    assert log.version == 1
    assert log.test_id == 7
    assert log.interface_id == 4
    assert log.rec_size == 8
    assert log.records[0].payload == first
    assert log.records[1].payload == second
    assert log.records[0].ole_time == ole_days(moment)


def test_short_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "short.DAT"
    path.write_bytes(b"\x2b\x1a")
    with pytest.raises(ValueError, match="not a binary log"):
        read_dat(path)
