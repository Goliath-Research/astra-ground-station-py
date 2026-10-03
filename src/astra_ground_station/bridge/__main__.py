"""Entry point for the OPC UA bridge service."""

from astra_ground_station.bridge import opcua_endpoint
from astra_ground_station.runtime import run_service


def main(argv: list[str] | None = None) -> int:
    # Resolve the configured endpoint so a broken bridge import fails at startup.
    opcua_endpoint()
    return run_service("astra-bridge", argv)


if __name__ == "__main__":
    raise SystemExit(main())
