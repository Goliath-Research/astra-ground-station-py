"""Select the accelerated backend.

Pure Python is the default and the only backend that works today. Mojo is
accepted for later performance-critical pieces, but this package does not
import it. The legacy C code via cffi is the other fallback, and it is not
wired in yet either.
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
            "ASTRA_NATIVE_BACKEND=mojo but no Python binding is built; "
            "unset the variable to use the pure-Python path"
        )
    raise RuntimeError("ASTRA_NATIVE_BACKEND must be 'python' or 'mojo'")
