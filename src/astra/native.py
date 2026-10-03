"""Select the packer backend.

The migration runs the integer-shift packer in Python first. Mojo
``pack_records`` / ``unpack_records`` is only for a later profile. This
package does not import Mojo. A C ABI via cffi is the fallback if a pinned
Mojo SDK cannot be called, and it is not wired in yet either.
"""

import os
from typing import Literal

BackendName = Literal["python"]


def active_backend() -> BackendName:
    """Return the backend the process will actually use."""
    requested = os.environ.get("ASTRA_NATIVE_BACKEND", "python")
    if requested == "python":
        return "python"
    if requested == "mojo":
        raise RuntimeError(
            "ASTRA_NATIVE_BACKEND=mojo but pack_records/unpack_records are not "
            "built; unset the variable to use the pure-Python path"
        )
    raise RuntimeError("ASTRA_NATIVE_BACKEND must be 'python' or 'mojo'")
