"""PostgreSQL checks. Skipped unless ``DATABASE_URL`` is set."""

import os
from pathlib import Path

import psycopg
import pytest

from astra_ground_station.db.connection import check_connection, database_url_from_env
from astra_ground_station.db.schema_loader import apply_schema

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL is not set",
)


def test_loader_connects_and_schemas_follow_scripts() -> None:
    url = database_url_from_env()
    schema_dir = Path(__file__).resolve().parents[1] / "database" / "schema"
    applied = apply_schema(url, schema_dir)
    check_connection(url)
    if not applied:
        return
    with psycopg.connect(url) as conn:
        rows = conn.execute(
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name IN ('config', 'testlog')
            ORDER BY schema_name
            """
        ).fetchall()
    present = [row[0] for row in rows]
    assert present == ["config", "testlog"]
