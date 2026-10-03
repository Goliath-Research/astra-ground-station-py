"""Expected database failures that callers can report without a traceback."""


class DatabaseError(Exception):
    """Base type for configuration and schema-load failures."""


class DatabaseConfigError(DatabaseError):
    """``DATABASE_URL`` is missing, not a PostgreSQL URL, or the server is down."""


class SchemaLoadError(DatabaseError):
    """A schema script is missing, forbidden, or ``psql`` rejected it."""
