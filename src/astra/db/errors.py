"""Expected database failures that callers can report without a traceback."""

from typing import Literal

ConfigCode = Literal["invalid", "not_found", "conflict"]


class DatabaseError(Exception):
    """Base type for configuration and schema-load failures."""


class DatabaseConfigError(DatabaseError):
    """``DATABASE_URL`` is missing, not a PostgreSQL URL, or the server is down."""


class SchemaLoadError(DatabaseError):
    """A schema script is missing, forbidden, or ``psql`` rejected it."""


class ConfigError(DatabaseError):
    """A config write was rejected.

    ``code`` is the only text that should reach an operator. It is one of
    ``invalid``, ``not_found``, or ``conflict``, and it never includes a
    password, a token, or a connection URL.
    """

    def __init__(self, code: ConfigCode) -> None:
        super().__init__(code)
        self.code: ConfigCode = code
