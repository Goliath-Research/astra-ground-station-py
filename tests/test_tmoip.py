import pytest

from astra.settings import stage_count as configured_stage_count
from astra.tmoip import (
    frame_due,
    minor_frame_packet_id,
    reassemble,
    stage_count,
    stage_port,
    stage_ports,
)
from astra.tmoip.__main__ import main


def test_default_stage_ports_follow_the_delphi_decoder() -> None:
    assert stage_count({}) == 2
    assert stage_port(1, {}) == 2358
    assert stage_port(2, {}) == 2359
    assert stage_ports({}) == (2358, 2359)
    assert main(["--check"]) == 0


def test_minor_frame_ids_follow_stage_count() -> None:
    # TAstraDecoder: packet id 100 * (stage - 1) + 106. The count is settings.
    count = configured_stage_count({})
    assert count == 2
    assert [minor_frame_packet_id(stage) for stage in range(1, count + 1)] == [106, 206]
    assert minor_frame_packet_id(3) == 306


def test_encoder_rate_rule() -> None:
    # AstraTMEncoder: Sequence * packetRate mod irigRate = 0.
    assert frame_due(0, 100, 200)
    assert not frame_due(1, 100, 200)
    assert frame_due(2, 100, 200)
    assert frame_due(5, 0, 200)


def test_reassembly_is_not_ported() -> None:
    with pytest.raises(NotImplementedError, match="TMoIP"):
        reassemble(b"")
