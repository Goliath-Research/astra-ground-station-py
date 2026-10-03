"""Entry point for the log-exporter service."""

from astra.exporter import export_job
from astra.runtime import run_service


def main(argv: list[str] | None = None) -> int:
    if not callable(export_job):
        raise RuntimeError("exporter entry point is not wired")
    return run_service("astra-exporter", argv)


if __name__ == "__main__":
    raise SystemExit(main())
