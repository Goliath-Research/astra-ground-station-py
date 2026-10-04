"""Interface CSV generator.

Four arguments, matching the Delphi error text: stage, smart node, packet,
and the CSV path. The lookup is ``spgetnodeid``. The file is the Simulink
CSV from ``spgetinterface``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from astra.db.config_repo import ConfigRepo
from astra.db.connection import connect, database_url_from_env
from astra.db.errors import ConfigError, DatabaseConfigError
from astra.web.csv_text import INTERFACE_COLUMNS, csv_document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m astra.cli.generate",
        description="Write the Simulink interface CSV for one packet node.",
    )
    parser.add_argument("--check", action="store_true", help="Exit without generating")
    parser.add_argument("stage", nargs="?")
    parser.add_argument("node", nargs="?")
    parser.add_argument("interface", nargs="?")
    parser.add_argument("csv_path", nargs="?")
    args = parser.parse_args(argv)
    if args.check:
        return 0
    if args.stage is None or args.node is None or args.interface is None or args.csv_path is None:
        parser.print_usage(sys.stderr)
        return 2
    try:
        url = database_url_from_env()
    except DatabaseConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    try:
        with connect(url) as conn:
            repo = ConfigRepo(conn)
            node_id = repo.interface_node_id(args.stage, args.node, args.interface)
            document = csv_document(INTERFACE_COLUMNS, repo.interface_rows(node_id))
    except DatabaseConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    except ConfigError as exc:
        print(exc.code, file=sys.stderr)
        return 1
    try:
        Path(args.csv_path).write_text(document, encoding="utf-8", newline="")
    except OSError:
        print("could not write the csv", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
