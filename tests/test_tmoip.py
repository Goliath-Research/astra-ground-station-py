import pytest

from astra.tmoip import reassemble, stage_count, stage_port, stage_ports
from astra.tmoip.__main__ import main


def test_default_stage_ports_follow_the_delphi_decoder() -> None:
    assert stage_count({}) == 2
    assert stage_port(1, {}) == 2358
    assert stage_port(2, {}) == 2359
    assert stage_ports({}) == (2358, 2359)
    assert main(["--check"]) == 0


def test_reassembly_is_not_ported() -> None:
    with pytest.raises(NotImplementedError, match="TMoIP"):
        reassemble(b"")
