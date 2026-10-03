"""Apply ``database/schema/*.sql`` with ``psql``.

PL/pgSQL function bodies contain semicolons, so the files are not split in
Python. ``psql`` is required only when at least one script is present.
``02_data.sql`` is refused: it is a data dump, not a schema.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from astra_ground_station.db.connection import check_connection, database_url_from_env
from astra_ground_station.db.errors import DatabaseError, SchemaLoadError

_DATA_DUMP = "02_data.sql"


def default_schema_dir() -> Path:
    """Return ``ASTRA_SCHEMA_DIR`` or ``./database/schema``."""
    override = os.environ.get("ASTRA_SCHEMA_DIR", "").strip()
    if override:
        return Path(override)
    return Path.cwd() / "database" / "schema"


def list_schema_files(schema_dir: Path) -> list[Path]:
    """Return ``*.sql`` files in lexical order.

    Raises:
        SchemaLoadError: the directory is missing or contains ``02_data.sql``.
    """
    if not schema_dir.is_dir():
        raise SchemaLoadError(f"schema directory does not exist: {schema_dir}")
    dump = [path.name for path in schema_dir.iterdir() if path.name.lower() == _DATA_DUMP]
    if dump:
        raise SchemaLoadError("refusing to load data dump 02_data.sql; schema scripts only")
    return sorted(path for path in schema_dir.iterdir() if path.is_file() and path.suffix == ".sql")


def apply_schema(database_url: str, schema_dir: Path) -> list[Path]:
    """Check connectivity, then apply each schema file.

    Returns the files that were applied. An empty schema directory is valid:
    the database is reachable and there is nothing to load yet.
    """
    files = list_schema_files(schema_dir)
    check_connection(database_url)
    if not files:
        return []
    if shutil.which("psql") is None:
        raise SchemaLoadError("psql is not on PATH; install postgresql-client to load schema files")
    for path in files:
        _apply_file(database_url, path)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="astra-load-schema")
    parser.add_argument(
        "--schema-dir",
        type=Path,
        default=None,
        help="Directory of *.sql files (default: ./database/schema or ASTRA_SCHEMA_DIR)",
    )
    args = parser.parse_args(argv)
    schema_dir = args.schema_dir if args.schema_dir is not None else default_schema_dir()
    try:
        applied = apply_schema(database_url_from_env(), schema_dir)
    except DatabaseError as exc:
        print(f"astra-load-schema: {exc}", file=sys.stderr)
        return 2
    if applied:
        names = ", ".join(path.name for path in applied)
        print(f"applied {len(applied)} schema file(s): {names}")
    else:
        print("database reachable; no schema files to apply")
    return 0


def _apply_file(database_url: str, path: Path) -> None:
    result = subprocess.run(
        ["psql", "--dbname", database_url, "-v", "ON_ERROR_STOP=1", "-f", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "psql exited with a non-zero status"
        raise SchemaLoadError(f"psql failed for {path.name}: {detail}")


if __name__ == "__main__":
    raise SystemExit(main())
