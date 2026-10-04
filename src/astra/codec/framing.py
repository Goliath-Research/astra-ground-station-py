"""UDP datagram framing from ``TAstraNetPacket``.

``GetIdPayload`` / ``SetIdPayload`` move a Delphi ``integer``, which is a
signed 32-bit little-endian value on Win64. ``GetDeviceT_MS`` reads the
first four payload bytes the same way and does not look at the field table.

There is no checksum on this frame. A checksum that is computed, including
a Chapter 10 checksum, keeps the low bits of its field width
(``truncate_checksum``). Chapter 10 sync and TMATS are not on the live
path, and the migration plan describes no SLIP or UART wrapper.
"""

import struct

from astra.codec.errors import CodecError

_INT32 = struct.Struct("<i")


def pack_id_payload(packet_id: int, payload: bytes) -> bytes:
    """Return a datagram of ``packet_id`` followed by ``payload``."""
    if isinstance(packet_id, bool) or not isinstance(packet_id, int):
        raise CodecError("packet id must be an int")
    if packet_id < -0x80000000 or packet_id > 0x7FFFFFFF:
        raise CodecError(f"packet id {packet_id} does not fit in a signed 32-bit integer")
    if not isinstance(payload, (bytes, bytearray)):
        raise CodecError("payload must be bytes")
    return _INT32.pack(packet_id) + bytes(payload)


def unpack_id_payload(datagram: bytes) -> tuple[int, bytes]:
    """Split a datagram into ``(packet_id, payload)``."""
    if len(datagram) < _INT32.size:
        raise CodecError(f"datagram is {len(datagram)} bytes; an id needs {_INT32.size}")
    packet_id: int
    (packet_id,) = _INT32.unpack_from(datagram, 0)
    return packet_id, bytes(datagram[_INT32.size :])


def device_t_ms(payload: bytes) -> int:
    """Return the leading ``t_ms`` integer of a payload."""
    if len(payload) < _INT32.size:
        raise CodecError(f"payload is {len(payload)} bytes; t_ms needs {_INT32.size}")
    t_ms: int
    (t_ms,) = _INT32.unpack_from(payload, 0)
    return t_ms
