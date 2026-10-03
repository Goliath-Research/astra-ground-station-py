"""PostgreSQL connectivity.

Services use one database and the schemas ``config`` and ``testlog``.
Session ``search_path`` follows the comment at the end of
``03_programmability.sql``.
"""

import os
from collections.abc import Mapping
from typing import Any

import psycopg

from astra.db.errors import DatabaseConfigError

DEFAULT_SEARCH_PATH = "config, testlog, public"


def database_url_from_env(environ: Mapping[str, str] | None = None) -> str:
    """Read ``DATABASE_URL`` without echoing it back in errors."""
    env = os.environ if environ is None else environ
    url = env.get("DATABASE_URL", "").strip()
    if not url:
        raise DatabaseConfigError("DATABASE_URL is not set")
    if not url.startswith(("postgresql://", "postgres://")):
        raise DatabaseConfigError("DATABASE_URL must be a postgresql:// URL")
    return url


def connect(database_url: str) -> psycopg.Connection[Any]:
    """Open a connection and set ``search_path``.

    Failures are reported without the URL, which may contain a password.
    The caller closes the connection.
    """
    try:
        conn = psycopg.connect(database_url)
    except psycopg.Error:
        raise DatabaseConfigError("could not connect to PostgreSQL") from None
    try:
        conn.execute("SELECT set_config('search_path', %s, false)", (DEFAULT_SEARCH_PATH,))
    except psycopg.Error:
        conn.close()
        raise DatabaseConfigError("could not connect to PostgreSQL") from None
    return conn


def check_connection(database_url: str) -> None:
    """Open a connection and run ``SELECT 1``."""
    try:
        with connect(database_url) as conn:
            row = conn.execute("SELECT 1").fetchone()
    except DatabaseConfigError:
        raise
    except psycopg.Error:
        raise DatabaseConfigError("could not connect to PostgreSQL") from None
    if row is None or row[0] != 1:
        raise DatabaseConfigError("database connectivity check failed")
