"""Headless minor-frame encoder. The DevExpress grid is not ported."""

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m astra.cli.tm_encoder")
    parser.add_argument("--check", action="store_true", help="Exit without encoding")
    args = parser.parse_args(argv)
    if args.check:
        return 0
    raise NotImplementedError("TM encoder is not ported")


if __name__ == "__main__":
    raise SystemExit(main())
