import struct

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from astra.binlog import CHECK, HEADER, MAGIC, OLE_EPOCH, dat_filename, read_dat


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


def test_reader_is_not_ported() -> None:
    with pytest.raises(NotImplementedError, match="binary log"):
        read_dat("LOG-T1-I1.DAT")
