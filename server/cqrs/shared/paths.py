"""Shared CQRS database URL helpers."""

from __future__ import annotations

import os
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = SERVER_ROOT / "data"

DEFAULT_POSTGRES_USER = "user"
DEFAULT_POSTGRES_PASSWORD = "password"
DEFAULT_POSTGRES_HOST = "127.0.0.1"
DEFAULT_POSTGRES_PORT = "5432"


def postgres_url(database: str, *, host: str | None = None) -> str:
    """Build an async Postgres URL for a database name."""
    resolved_host = host or os.getenv("CQRS_POSTGRES_HOST", DEFAULT_POSTGRES_HOST)
    port = os.getenv("CQRS_POSTGRES_PORT", DEFAULT_POSTGRES_PORT)
    user = os.getenv("CQRS_POSTGRES_USER", DEFAULT_POSTGRES_USER)
    password = os.getenv("CQRS_POSTGRES_PASSWORD", DEFAULT_POSTGRES_PASSWORD)
    return f"postgresql+asyncpg://{user}:{password}@{resolved_host}:{port}/{database}"


def normalize_async_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url
