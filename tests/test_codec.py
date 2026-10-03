import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from astra_ground_station.codec import prefix_u32_le, split_u32_le


@settings(deadline=None, derandomize=True)
@given(st.binary(max_size=4096))
def test_length_prefix_round_trip(payload: bytes) -> None:
    assert split_u32_le(prefix_u32_le(payload)) == payload


def test_split_rejects_truncated_frame() -> None:
    with pytest.raises(ValueError, match="uint32"):
        split_u32_le(b"\x01\x00")
