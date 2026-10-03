"""Entry point for the TMoIP service."""

from astra.runtime import run_service
from astra.tmoip import reassemble, stage_port


def main(argv: list[str] | None = None) -> int:
    if stage_port(1) != 2358 or not callable(reassemble):
        raise RuntimeError("TMoIP entry points are not wired")
    return run_service("astra-tmoip", argv)


if __name__ == "__main__":
    raise SystemExit(main())
