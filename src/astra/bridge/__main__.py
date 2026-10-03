"""Entry point for the bridge service."""

from astra.bridge import endpoint, tag_path
from astra.runtime import run_service


def main(argv: list[str] | None = None) -> int:
    # Importing the OPC UA surface fails startup if that package is broken.
    endpoint()
    tag_path("R2L", "t_ms")
    return run_service("astra-bridge", argv)


if __name__ == "__main__":
    raise SystemExit(main())
