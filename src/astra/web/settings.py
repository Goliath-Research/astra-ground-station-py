"""Process settings for the operator web app.

The bearer token and the database URL are read from the environment. Neither
value is included in an error string.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from astra.db.connection import database_url_from_env
from astra.db.errors import DatabaseConfigError

MIN_TOKEN_LENGTH = 16


@dataclass(frozen=True, slots=True)
class WebSettings:
    """Resolved settings for one process."""

    database_url: str | None
    token: str | None
    database_error: str | None
    token_error: str | None


def web_settings_from_env(environ: Mapping[str, str] | None = None) -> WebSettings:
    """Read ``DATABASE_URL`` and ``ASTRA_WEB_TOKEN``.

    A token shorter than 16 characters is treated as unset. The rejected
    value is not copied into ``token_error``.
    """
    env = os.environ if environ is None else environ
    raw_token = env.get("ASTRA_WEB_TOKEN", "").strip()
    if not raw_token:
        token: str | None = None
        token_error: str | None = "ASTRA_WEB_TOKEN is not set"
    elif len(raw_token) < MIN_TOKEN_LENGTH:
        token = None
        token_error = "ASTRA_WEB_TOKEN must be at least 16 characters"
    else:
        token = raw_token
        token_error = None

    raw_url = env.get("DATABASE_URL", "").strip()
    if not raw_url:
        return WebSettings(
            database_url=None,
            token=token,
            database_error="DATABASE_URL is not set",
            token_error=token_error,
        )
    try:
        url = database_url_from_env(env)
    except DatabaseConfigError as exc:
        return WebSettings(
            database_url=None,
            token=token,
            database_error=str(exc),
            token_error=token_error,
        )
    return WebSettings(
        database_url=url,
        token=token,
        database_error=None,
        token_error=token_error,
    )
