"""Entry point for the bridge service."""

from astra.bridge import bridge_port, endpoint, tag_path
from astra.runtime import run_service


def main(argv: list[str] | None = None) -> int:
    # Reading configuration and the OPC UA surface fails startup if either is broken.
    bridge_port()
    endpoint()
    tag_path("R2L", "t_ms")
    return run_service("astra-bridge", argv)


if __name__ == "__main__":
    raise SystemExit(main())
