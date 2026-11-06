"""UTC helpers compatible with Postgres TIMESTAMP WITHOUT TIME ZONE + asyncpg."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def ensure_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def parse_utc_naive(value: Any) -> datetime:
    if isinstance(value, datetime):
        return ensure_utc_naive(value)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        return ensure_utc_naive(parsed)
    return utcnow()
