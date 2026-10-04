"""UDP bridge.

One process replaces ``AstraBridgeServer`` and ``AstraBridgeServerDesktop``.
It will poll ``config.tests``, bind ``ASTRA_BRIDGE_PORT`` (default 2357),
write ``.DAT`` files, and publish OPC UA tags through :mod:`astra.opcua`.
The accept check below is the part ``IdUDPServerUDPRead`` specifies. The
socket loop is not running yet.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from astra.codec.framing import device_t_ms
from astra.opcua import endpoint, tag_path
from astra.settings import bridge_port

__all__ = ["DeviceRow", "accept_datagram", "bridge_port", "endpoint", "tag_path"]


@dataclass(frozen=True, slots=True)
class DeviceRow:
    """The interface size and peer address the bridge compares."""

    payload_size: int
    peer_ip: str


def accept_datagram(
    interface_id: int,
    payload: bytes,
    peer_ip: str,
    devices: Mapping[int, DeviceRow],
    last_t_ms: int,
) -> int | None:
    """Return the new ``t_ms`` when the datagram is accepted.

    Order is the bridge check: known interface id, ``len(payload)`` equal to
    the interface packet size, peer IP equal to the device row, then the
    first four payload bytes as a signed int32 strictly greater than
    ``last_t_ms``. That read is not a field lookup. A rejected datagram
    returns ``None`` and leaves ``last_t_ms`` unchanged.
    """
    device = devices.get(interface_id)
    if device is None:
        return None
    if len(payload) != device.payload_size:
        return None
    if peer_ip != device.peer_ip:
        return None
    if len(payload) < 4:
        return None
    t_ms = device_t_ms(payload)
    if t_ms <= last_t_ms:
        return None
    return t_ms
