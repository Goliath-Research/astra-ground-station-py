"""Bench UDP peer. Sends synthetic R2L datagrams once phase 3 lands."""

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m astra.cli.device")
    parser.add_argument("--check", action="store_true", help="Exit without sending")
    args = parser.parse_args(argv)
    if args.check:
        return 0
    raise NotImplementedError("device simulator is not ported")


if __name__ == "__main__":
    raise SystemExit(main())
