"""Write-side database session factory. Never import this from the query service."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy import MetaData, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from ...shared.paths import normalize_async_database_url, postgres_url

COMMAND_DATABASE_URL = normalize_async_database_url(
    os.getenv(
        "CQRS_COMMAND_DATABASE_URL",
        os.getenv("CQRS_DATABASE_URL", postgres_url("cqrs_command")),
    )
)

command_metadata = MetaData()


class CommandSQLModel(SQLModel):
    metadata = command_metadata


_engine_kwargs: dict = {}
if os.getenv("CQRS_BROKER_MODE", "").lower() == "memory":
    _engine_kwargs["poolclass"] = NullPool

engine = create_async_engine(COMMAND_DATABASE_URL, echo=False, **_engine_kwargs)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_write_db() -> None:
    from . import models as _models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(command_metadata.create_all)
        await connection.run_sync(_ensure_write_schema)


def _ensure_write_schema(connection) -> None:
    inspector = inspect(connection)
    if inspector.has_table("raw_log_events"):
        columns = {column["name"] for column in inspector.get_columns("raw_log_events")}
        if "source_log_id" not in columns:
            connection.execute(
                text("ALTER TABLE raw_log_events ADD COLUMN source_log_id INTEGER")
            )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_raw_log_events_source_log_id "
                    "ON raw_log_events (source_log_id)"
                )
            )
        if "content_hash" not in columns:
            connection.execute(
                text("ALTER TABLE raw_log_events ADD COLUMN content_hash TEXT")
            )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_raw_log_events_content_hash "
                    "ON raw_log_events (content_hash)"
                )
            )
        if "actor_id" not in columns:
            connection.execute(
                text("ALTER TABLE raw_log_events ADD COLUMN actor_id TEXT")
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_raw_log_events_actor_id "
                    "ON raw_log_events (actor_id)"
                )
            )
        if "tournament_id" not in columns:
            connection.execute(
                text("ALTER TABLE raw_log_events ADD COLUMN tournament_id TEXT")
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_raw_log_events_tournament_id "
                    "ON raw_log_events (tournament_id)"
                )
            )

    if inspector.has_table("outbox_events"):
        outbox_columns = {
            column["name"] for column in inspector.get_columns("outbox_events")
        }
        if "next_attempt_at" not in outbox_columns:
            connection.execute(
                text("ALTER TABLE outbox_events ADD COLUMN next_attempt_at TIMESTAMP")
            )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_outbox_events_status_created_at "
                "ON outbox_events (status, created_at)"
            )
        )

    if inspector.has_table("events"):
        event_columns = {column["name"] for column in inspector.get_columns("events")}
        if "event_slug" in event_columns and "slug" not in event_columns:
            connection.execute(
                text("ALTER TABLE events RENAME COLUMN event_slug TO slug")
            )

    if inspector.has_table("tournaments"):
        tournament_columns = {
            column["name"] for column in inspector.get_columns("tournaments")
        }
        if "event_id" not in tournament_columns:
            connection.execute(text("ALTER TABLE tournaments ADD COLUMN event_id TEXT"))
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_tournaments_event_id "
                    "ON tournaments (event_id)"
                )
            )


async def get_write_session() -> AsyncGenerator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
