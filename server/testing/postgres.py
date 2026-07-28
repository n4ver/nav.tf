"""Postgres test database helpers."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool


def postgres_test_url(database: str) -> str:
    host = os.getenv("CQRS_POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("CQRS_POSTGRES_PORT", "5432")
    user = os.getenv("CQRS_POSTGRES_USER", "user")
    password = os.getenv("CQRS_POSTGRES_PASSWORD", "password")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"


def normalize_postgres_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def sync_truncate_database(database: str) -> None:
    """Sync TRUNCATE for test isolation without async loop conflicts."""
    import psycopg2

    host = os.getenv("CQRS_POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("CQRS_POSTGRES_PORT", "5432")
    user = os.getenv("CQRS_POSTGRES_USER", "user")
    password = os.getenv("CQRS_POSTGRES_PASSWORD", "password")

    connection = psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname=database,
    )
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
            )
            tables = [row[0] for row in cursor.fetchall()]
            if tables:
                quoted = ", ".join(f'"{name}"' for name in tables)
                cursor.execute(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE")
    finally:
        connection.close()


async def reset_postgres_schema(
    engine: AsyncEngine,
    metadata: MetaData,
    init_fn: Callable[[], Awaitable[Any]] | None = None,
) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(metadata.drop_all)
        await connection.run_sync(metadata.create_all)
    if init_fn is not None:
        await init_fn()


def create_postgres_engine(database: str) -> AsyncEngine:
    return create_async_engine(
        normalize_postgres_url(postgres_test_url(database)),
        echo=False,
        poolclass=NullPool,
    )


def dispose_engine(engine: AsyncEngine) -> None:
    engine.sync_engine.dispose()

