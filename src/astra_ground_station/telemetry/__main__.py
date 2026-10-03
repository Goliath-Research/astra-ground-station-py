"""Entry point for the telemetry service."""

from astra_ground_station.runtime import run_service
from astra_ground_station.telemetry import decode_frame, encode_frame


def main(argv: list[str] | None = None) -> int:
    # A broken decoder or encoder import fails here, before the idle loop.
    if not callable(decode_frame) or not callable(encode_frame):
        raise RuntimeError("telemetry decoder and encoder must be callable")
    return run_service("astra-telemetry", argv)


if __name__ == "__main__":
    raise SystemExit(main())
