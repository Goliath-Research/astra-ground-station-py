"""Entry point for the TMoIP service."""

from astra.runtime import run_service
from astra.settings import bridge_port, stage_count, stage_ports
from astra.tmoip import reassemble


def main(argv: list[str] | None = None) -> int:
    ports = stage_ports()
    if len(ports) != stage_count() or ports[0] != bridge_port() + 1 or not callable(reassemble):
        raise RuntimeError("TMoIP entry points are not wired")
    return run_service("astra-tmoip", argv)


if __name__ == "__main__":
    raise SystemExit(main())
