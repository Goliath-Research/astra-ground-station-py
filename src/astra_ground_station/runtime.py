"""Shared process loop for the long-running services."""

import argparse
import logging
import signal
import threading
from types import FrameType


def run_service(service_name: str, argv: list[str] | None = None) -> int:
    """Run a scaffold service, or exit immediately with ``--check``."""
    parser = argparse.ArgumentParser(prog=service_name)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Import the entry point and exit without serving",
    )
    args = parser.parse_args(argv)
    if args.check:
        return 0
    return serve_until_signal(service_name)


def serve_until_signal(service_name: str) -> int:
    """Idle until SIGINT or SIGTERM.

    The real service bodies are not ported. The unit files still have a
    process that stays up and shuts down cleanly.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger(service_name)
    stop = threading.Event()

    def handle(signum: int, _frame: FrameType | None) -> None:
        log.info("received signal %s", signum)
        stop.set()

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)
    log.info("%s placeholder is idle; business logic is not ported", service_name)
    stop.wait()
    log.info("%s stopping", service_name)
    return 0
