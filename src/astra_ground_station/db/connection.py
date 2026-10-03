"""PostgreSQL connectivity. No queries beyond a liveness check live here yet."""

import os
from collections.abc import Mapping

import psycopg

from astra_ground_station.db.errors import DatabaseConfigError


def database_url_from_env(environ: Mapping[str, str] | None = None) -> str:
    """Read ``DATABASE_URL`` without echoing it back in errors."""
    env = os.environ if environ is None else environ
    url = env.get("DATABASE_URL", "").strip()
    if not url:
        raise DatabaseConfigError("DATABASE_URL is not set")
    if not url.startswith(("postgresql://", "postgres://")):
        raise DatabaseConfigError("DATABASE_URL must be a postgresql:// URL")
    return url


def check_connection(database_url: str) -> None:
    """Open a connection and run ``SELECT 1``.

    Connection failures are reported without the URL, which may contain a
    password.
    """
    try:
        with psycopg.connect(database_url) as conn:
            row = conn.execute("SELECT 1").fetchone()
    except psycopg.Error:
        raise DatabaseConfigError("could not connect to PostgreSQL") from None
    if row is None or row[0] != 1:
        raise DatabaseConfigError("database connectivity check failed")
