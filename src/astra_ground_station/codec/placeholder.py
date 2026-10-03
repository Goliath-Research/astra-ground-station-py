"""Scaffold framing helpers. Not the Astra wire codec."""


def prefix_u32_le(payload: bytes) -> bytes:
    """Prefix ``payload`` with its length as a little-endian uint32."""
    if len(payload) > 0xFFFFFFFF:
        raise ValueError("payload does not fit in a uint32 length")
    return len(payload).to_bytes(4, "little") + payload


def split_u32_le(frame: bytes) -> bytes:
    """Return the payload of a frame produced by :func:`prefix_u32_le`."""
    if len(frame) < 4:
        raise ValueError("frame is shorter than a uint32 length prefix")
    length = int.from_bytes(frame[:4], "little")
    payload = frame[4:]
    if length != len(payload):
        raise ValueError("length prefix does not match payload")
    return payload
