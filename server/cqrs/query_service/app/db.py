"""Read-side database session factory. Never import this from the command service."""

from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy import MetaData, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from ...shared.paths import normalize_async_database_url, postgres_url

QUERY_DATABASE_URL = normalize_async_database_url(
    os.getenv(
        "CQRS_QUERY_DATABASE_URL",
        postgres_url("cqrs_query"),
    )
)

query_metadata = MetaData()


class QuerySQLModel(SQLModel):
    metadata = query_metadata


_engine_kwargs: dict = {}
if os.getenv("CQRS_BROKER_MODE", "").lower() == "memory":
    _engine_kwargs["poolclass"] = NullPool

engine = create_async_engine(QUERY_DATABASE_URL, echo=False, **_engine_kwargs)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_read_db() -> None:
    from . import models as _models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(query_metadata.create_all)
        await connection.run_sync(_ensure_read_schema)


def _ensure_read_schema(connection) -> None:
    inspector = inspect(connection)
    if inspector.has_table("match_summary_view"):
        columns = {column["name"] for column in inspector.get_columns("match_summary_view")}
        if "tournament_id" not in columns:
            connection.execute(text("ALTER TABLE match_summary_view ADD COLUMN tournament_id TEXT"))
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_match_summary_view_tournament_id "
                    "ON match_summary_view (tournament_id)"
                )
            )
        if "source_log_id" not in columns:
            connection.execute(text("ALTER TABLE match_summary_view ADD COLUMN source_log_id INTEGER"))
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_match_summary_view_source_log_id "
                    "ON match_summary_view (source_log_id)"
                )
            )
        if "ratings_ready" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE match_summary_view ADD COLUMN ratings_ready BOOLEAN DEFAULT FALSE"
                )
            )

    if inspector.has_table("player_match_stats_view"):
        columns = {column["name"] for column in inspector.get_columns("player_match_stats_view")}
        alterations = {
            "primary_class": "ALTER TABLE player_match_stats_view ADD COLUMN primary_class TEXT DEFAULT 'unknown'",
            "playtime_seconds": "ALTER TABLE player_match_stats_view ADD COLUMN playtime_seconds INTEGER DEFAULT 0",
            "rating": "ALTER TABLE player_match_stats_view ADD COLUMN rating REAL DEFAULT 1.0",
        }
        for name, ddl in alterations.items():
            if name not in columns:
                connection.execute(text(ddl))

    if inspector.has_table("player_lifetime_stats_view"):
        columns = {column["name"] for column in inspector.get_columns("player_lifetime_stats_view")}
        if "average_rating" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE player_lifetime_stats_view ADD COLUMN average_rating REAL DEFAULT 1.0"
                )
            )

    if inspector.has_table("class_rating_benchmark_view"):
        columns = {column["name"] for column in inspector.get_columns("class_rating_benchmark_view")}
        if "class_id" not in columns:
            connection.execute(text("DROP TABLE class_rating_benchmark_view"))
            from .models import ClassRatingBenchmarkProjection

            ClassRatingBenchmarkProjection.__table__.create(connection, checkfirst=True)

    if not inspector.has_table("player_match_class_stats_view"):
        from .models import PlayerMatchClassStatsProjection

        PlayerMatchClassStatsProjection.__table__.create(connection, checkfirst=True)

    if not inspector.has_table("leaderboard_snapshot_view"):
        from .models import LeaderboardSnapshotProjection

        LeaderboardSnapshotProjection.__table__.create(connection, checkfirst=True)

    if not inspector.has_table("player_identity_view"):
        from .models import PlayerIdentityProjection

        PlayerIdentityProjection.__table__.create(connection, checkfirst=True)
    elif inspector.has_table("player_identity_view"):
        columns = {column["name"] for column in inspector.get_columns("player_identity_view")}
        if "custom_alias" not in columns:
            connection.execute(
                text("ALTER TABLE player_identity_view ADD COLUMN custom_alias TEXT")
            )


async def get_read_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
