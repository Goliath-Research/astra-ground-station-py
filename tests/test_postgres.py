"""PostgreSQL checks. Skipped unless ``DATABASE_URL`` is set."""

import os
from pathlib import Path

import psycopg
import pytest

from astra.db.connection import DEFAULT_SEARCH_PATH, connect, database_url_from_env
from astra.db.schema_loader import apply_schema

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL is not set",
)

_FUNCTIONS = (
    ("config", "spcalcvartypesizes"),
    ("testlog", "spimportvalues"),
)


def _function_count(url: str) -> int:
    with psycopg.connect(url) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM pg_proc AS p
            JOIN pg_namespace AS n ON n.oid = p.pronamespace
            WHERE (n.nspname, p.proname) IN (
                ('config', 'spcalcvartypesizes'),
                ('testlog', 'spimportvalues')
            )
            """
        ).fetchone()
    if row is None:
        return 0
    count = row[0]
    if not isinstance(count, int):
        raise AssertionError("function count was not an integer")
    return count


def test_schema_scripts_load_config_and_testlog() -> None:
    url = database_url_from_env()
    schema_dir = Path(__file__).resolve().parents[1] / "database" / "schema"
    if _function_count(url) < len(_FUNCTIONS):
        applied = [path.name for path in apply_schema(url, schema_dir)]
        assert applied == ["01_schema.sql", "03_programmability.sql"]
    assert _function_count(url) == len(_FUNCTIONS)
    with psycopg.connect(url) as conn:
        schemas = conn.execute(
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name IN ('config', 'testlog')
            ORDER BY schema_name
            """
        ).fetchall()
        collations = conn.execute(
            """
            SELECT n.nspname
            FROM pg_collation AS c
            JOIN pg_namespace AS n ON n.oid = c.collnamespace
            WHERE n.nspname IN ('config', 'testlog') AND c.collname = 'mssql_order'
            ORDER BY n.nspname
            """
        ).fetchall()
    assert [row[0] for row in schemas] == ["config", "testlog"]
    assert [row[0] for row in collations] == ["config", "testlog"]
    with connect(url) as conn:
        search_path = conn.execute("SHOW search_path").fetchone()
    assert search_path is not None
    assert search_path[0] == DEFAULT_SEARCH_PATH
