"""Bit-at-a-time stand-in for ``TBitStream.SaveBit``.

``docs/MIGRATION.md`` §5 says ``SavePacket`` zero-fills the buffer and
``SaveBit`` ORs one bit at a time, least-significant bit of the value
first. This is that loop. It is not the production packer, and it was
not run inside Delphi. Golden hex in the tests is written out by hand
and checked against this loop so the two descriptions cannot drift
silently.
"""


def save_bits(parts: list[tuple[int, int]]) -> bytes:
    """OR each ``(width, bits)`` pair into a cleared buffer."""
    total = sum(width for width, _bits in parts)
    buffer = bytearray((total + 7) // 8)
    position = 0
    for width, bits in parts:
        for offset in range(width):
            if (bits >> offset) & 1:
                buffer[position // 8] |= 1 << (position % 8)
            position += 1
    return bytes(buffer)
