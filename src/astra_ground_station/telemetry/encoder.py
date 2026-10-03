"""Uplink / frame encoder placeholder."""

from collections.abc import Mapping


def encode_frame(fields: Mapping[str, object]) -> bytes:
    """Encode one telemetry frame.

    Raises:
        NotImplementedError: always, until the Delphi encoder is ported.
    """
    del fields
    raise NotImplementedError("telemetry encoder is not ported")
