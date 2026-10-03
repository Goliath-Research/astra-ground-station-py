"""Downlink / frame decoder placeholder."""

from collections.abc import Mapping


def decode_frame(frame: bytes) -> Mapping[str, object]:
    """Decode one telemetry frame.

    Raises:
        NotImplementedError: always, until the Delphi decoder is ported.
    """
    del frame
    raise NotImplementedError("telemetry decoder is not ported")
