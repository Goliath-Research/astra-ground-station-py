import pytest

from astra_ground_station.telemetry import decode_frame, encode_frame
from astra_ground_station.telemetry.__main__ import main


def test_decoder_is_not_ported() -> None:
    with pytest.raises(NotImplementedError, match="decoder"):
        decode_frame(b"")


def test_encoder_is_not_ported() -> None:
    with pytest.raises(NotImplementedError, match="encoder"):
        encode_frame({})


def test_telemetry_check_entrypoint() -> None:
    assert main(["--check"]) == 0
