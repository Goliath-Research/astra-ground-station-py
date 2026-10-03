"""Interface CSV generator. Four arguments, matching the Delphi error text."""

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m astra.cli.generate",
        description="Write an interface CSV. Not ported yet.",
    )
    parser.add_argument("--check", action="store_true", help="Exit without generating")
    parser.add_argument("stage", nargs="?")
    parser.add_argument("node", nargs="?")
    parser.add_argument("interface", nargs="?")
    parser.add_argument("csv_path", nargs="?")
    args = parser.parse_args(argv)
    if args.check:
        return 0
    raise NotImplementedError("generator is not ported")


if __name__ == "__main__":
    raise SystemExit(main())
