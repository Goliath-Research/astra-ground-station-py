"""Entry point for the web service."""

from astra_ground_station.runtime import run_service
from astra_ground_station.web import WEB_STACK


def main(argv: list[str] | None = None) -> int:
    # WEB_STACK is referenced so importing the web package is part of startup.
    if not WEB_STACK:
        raise RuntimeError("web stack name is empty")
    return run_service("astra-web", argv)


if __name__ == "__main__":
    raise SystemExit(main())
