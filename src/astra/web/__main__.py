"""Entry point for the web application."""

import argparse
import os

import uvicorn

from astra.web import create_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="astra-web")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Build the application and exit without listening",
    )
    args = parser.parse_args(argv)
    app = create_app()
    if args.check:
        return 0
    host = os.environ.get("ASTRA_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("ASTRA_WEB_PORT", "8080"))
    uvicorn.run(app, host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
