"""JSON body checks for the operator API.

Failures are :class:`ConfigError` with code ``invalid``. The rejected value
is not included, so a password or token cannot leak through a 400 response.
"""

from __future__ import annotations

from typing import Any

from astra.db.errors import ConfigError


def object_body(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ConfigError("invalid")
    return payload


def reject_unknown(body: dict[str, Any], allowed: frozenset[str]) -> None:
    if set(body) - allowed:
        raise ConfigError("invalid")


def require_fields(body: dict[str, Any], required: frozenset[str]) -> None:
    if required - set(body):
        raise ConfigError("invalid")


def as_str(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        raise ConfigError("invalid")
    text = value.strip()
    if text == "" or len(text) > max_len:
        raise ConfigError("invalid")
    return text


def as_password(value: Any) -> str:
    """Accept a write-only password without trimming it."""
    if not isinstance(value, str) or value == "" or len(value) > 64:
        raise ConfigError("invalid")
    return value


def as_int(value: Any, *, minimum: int | None = None, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError("invalid")
    if minimum is not None and value < minimum:
        raise ConfigError("invalid")
    if maximum is not None and value > maximum:
        raise ConfigError("invalid")
    return value


def as_bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ConfigError("invalid")
    return value


def as_opt_str(value: Any, max_len: int) -> str | None:
    if value is None:
        return None
    return as_str(value, max_len)


def as_opt_int(value: Any, *, minimum: int | None = None, maximum: int | None = None) -> int | None:
    if value is None:
        return None
    return as_int(value, minimum=minimum, maximum=maximum)


def as_float(value: Any) -> float:
    """Accept a JSON number. Booleans and non-finite values are rejected."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError("invalid")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ConfigError("invalid")
    return number
