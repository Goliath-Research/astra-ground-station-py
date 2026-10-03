"""Frame codec.

The Delphi codec is not ported. ``prefix_u32_le`` is a scaffold helper so
property tests have a pure function to pin. It is not the wire format.
"""

from astra_ground_station.codec.placeholder import prefix_u32_le, split_u32_le

__all__ = ["prefix_u32_le", "split_u32_le"]
