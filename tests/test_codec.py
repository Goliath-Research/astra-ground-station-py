import pytest

from astra.codec import pack, unpack


def test_pack_and_unpack_are_not_ported() -> None:
    with pytest.raises(NotImplementedError, match="pack"):
        pack(())
    with pytest.raises(NotImplementedError, match="unpack"):
        unpack(b"")
