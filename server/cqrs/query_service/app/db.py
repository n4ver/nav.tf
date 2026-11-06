"""Read-side database session factory. Never import this from the command service."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

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
        columns = {
            column["name"] for column in inspector.get_columns("match_summary_view")
        }
        if "tournament_id" not in columns:
            connection.execute(
                text("ALTER TABLE match_summary_view ADD COLUMN tournament_id TEXT")
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_match_summary_view_tournament_id "
                    "ON match_summary_view (tournament_id)"
                )
            )
        if "source_log_id" not in columns:
            connection.execute(
                text("ALTER TABLE match_summary_view ADD COLUMN source_log_id INTEGER")
            )
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
        if "blu_score" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE match_summary_view ADD COLUMN blu_score INTEGER DEFAULT 0"
                )
            )
        if "red_score" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE match_summary_view ADD COLUMN red_score INTEGER DEFAULT 0"
                )
            )

    if inspector.has_table("player_match_stats_view"):
        columns = {
            column["name"]
            for column in inspector.get_columns("player_match_stats_view")
        }
        alterations = {
            "primary_class": "ALTER TABLE player_match_stats_view ADD COLUMN primary_class TEXT DEFAULT 'unknown'",
            "playtime_seconds": "ALTER TABLE player_match_stats_view ADD COLUMN playtime_seconds INTEGER DEFAULT 0",
            "rating": "ALTER TABLE player_match_stats_view ADD COLUMN rating REAL DEFAULT 1.0",
            "damage_received": "ALTER TABLE player_match_stats_view ADD COLUMN damage_received INTEGER DEFAULT 0",
            "heals_received": "ALTER TABLE player_match_stats_view ADD COLUMN heals_received INTEGER DEFAULT 0",
            "ubers": "ALTER TABLE player_match_stats_view ADD COLUMN ubers INTEGER DEFAULT 0",
            "drops": "ALTER TABLE player_match_stats_view ADD COLUMN drops INTEGER DEFAULT 0",
            "captures": "ALTER TABLE player_match_stats_view ADD COLUMN captures INTEGER DEFAULT 0",
            "headshots": "ALTER TABLE player_match_stats_view ADD COLUMN headshots INTEGER DEFAULT 0",
            "backstabs": "ALTER TABLE player_match_stats_view ADD COLUMN backstabs INTEGER DEFAULT 0",
            "airshots": "ALTER TABLE player_match_stats_view ADD COLUMN airshots INTEGER DEFAULT 0",
        }
        for name, ddl in alterations.items():
            if name not in columns:
                connection.execute(text(ddl))

    # Backfill player-level CDM fields from class projections when still zero.
    if inspector.has_table("player_match_stats_view") and inspector.has_table(
        "player_match_class_stats_view"
    ):
        class_columns = {
            column["name"]
            for column in inspector.get_columns("player_match_class_stats_view")
        }
        player_columns = {
            column["name"]
            for column in inspector.get_columns("player_match_stats_view")
        }

        # damage_received / heals_received live on class rows; ubers/drops are player-level only.
        if {"damage_received", "heals_received"}.issubset(class_columns) and {
            "damage_received",
            "heals_received",
        }.issubset(player_columns):
            connection.execute(
                text(
                    """
                    UPDATE player_match_stats_view AS p
                    SET
                        damage_received = c.damage_received,
                        heals_received = c.heals_received
                    FROM (
                        SELECT
                            steam_id,
                            match_id,
                            MAX(damage_received) AS damage_received,
                            MAX(heals_received) AS heals_received
                        FROM player_match_class_stats_view
                        GROUP BY steam_id, match_id
                    ) AS c
                    WHERE p.steam_id = c.steam_id
                      AND p.match_id = c.match_id
                      AND COALESCE(p.damage_received, 0) = 0
                      AND COALESCE(p.heals_received, 0) = 0
                      AND (
                        COALESCE(c.damage_received, 0) <> 0
                        OR COALESCE(c.heals_received, 0) <> 0
                      )
                    """
                )
            )

        if {"ubers", "drops"}.issubset(class_columns) and {"ubers", "drops"}.issubset(
            player_columns
        ):
            connection.execute(
                text(
                    """
                    UPDATE player_match_stats_view AS p
                    SET
                        ubers = c.ubers,
                        drops = c.drops
                    FROM (
                        SELECT
                            steam_id,
                            match_id,
                            SUM(ubers) AS ubers,
                            SUM(drops) AS drops
                        FROM player_match_class_stats_view
                        GROUP BY steam_id, match_id
                    ) AS c
                    WHERE p.steam_id = c.steam_id
                      AND p.match_id = c.match_id
                      AND COALESCE(p.ubers, 0) = 0
                      AND COALESCE(p.drops, 0) = 0
                      AND (
                        COALESCE(c.ubers, 0) <> 0
                        OR COALESCE(c.drops, 0) <> 0
                      )
                    """
                )
            )

        if {"captures", "headshots", "backstabs"}.issubset(class_columns) and {
            "captures",
            "headshots",
            "backstabs",
        }.issubset(player_columns):
            connection.execute(
                text(
                    """
                    UPDATE player_match_stats_view AS p
                    SET
                        captures = c.captures,
                        headshots = c.headshots,
                        backstabs = c.backstabs
                    FROM (
                        SELECT
                            steam_id,
                            match_id,
                            MAX(captures) AS captures,
                            MAX(headshots) AS headshots,
                            MAX(backstabs) AS backstabs
                        FROM player_match_class_stats_view
                        GROUP BY steam_id, match_id
                    ) AS c
                    WHERE p.steam_id = c.steam_id
                      AND p.match_id = c.match_id
                      AND COALESCE(p.captures, 0) = 0
                      AND COALESCE(p.headshots, 0) = 0
                      AND COALESCE(p.backstabs, 0) = 0
                      AND (
                        COALESCE(c.captures, 0) <> 0
                        OR COALESCE(c.headshots, 0) <> 0
                        OR COALESCE(c.backstabs, 0) <> 0
                      )
                    """
                )
            )
        if "airshots" in class_columns and "airshots" in player_columns:
            connection.execute(
                text(
                    """
                    UPDATE player_match_stats_view AS p
                    SET airshots = c.airshots
                    FROM (
                        SELECT
                            steam_id,
                            match_id,
                            MAX(airshots) AS airshots
                        FROM player_match_class_stats_view
                        GROUP BY steam_id, match_id
                    ) AS c
                    WHERE p.steam_id = c.steam_id
                      AND p.match_id = c.match_id
                      AND COALESCE(p.airshots, 0) = 0
                      AND COALESCE(c.airshots, 0) <> 0
                    """
                )
            )

    if inspector.has_table("player_lifetime_stats_view"):
        columns = {
            column["name"]
            for column in inspector.get_columns("player_lifetime_stats_view")
        }
        if "average_rating" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE player_lifetime_stats_view ADD COLUMN average_rating REAL DEFAULT 1.0"
                )
            )

    if inspector.has_table("class_rating_benchmark_view"):
        columns = {
            column["name"]
            for column in inspector.get_columns("class_rating_benchmark_view")
        }
        if "class_id" not in columns:
            connection.execute(text("DROP TABLE class_rating_benchmark_view"))
            from .models import ClassRatingBenchmarkProjection

            ClassRatingBenchmarkProjection.__table__.create(connection, checkfirst=True)

    if not inspector.has_table("player_match_class_stats_view"):
        from .models import PlayerMatchClassStatsProjection

        PlayerMatchClassStatsProjection.__table__.create(connection, checkfirst=True)
    elif inspector.has_table("player_match_class_stats_view"):
        class_table_columns = {
            column["name"]
            for column in inspector.get_columns("player_match_class_stats_view")
        }
        for legacy_column in (
            "captures",
            "headshots",
            "backstabs",
            "airshots",
            "ubers",
            "drops",
        ):
            if legacy_column in class_table_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE player_match_class_stats_view "
                        f"ALTER COLUMN {legacy_column} SET DEFAULT 0"
                    )
                )

    if not inspector.has_table("leaderboard_snapshot_view"):
        from .models import LeaderboardSnapshotProjection

        LeaderboardSnapshotProjection.__table__.create(connection, checkfirst=True)

    if not inspector.has_table("player_identity_view"):
        from .models import PlayerIdentityProjection

        PlayerIdentityProjection.__table__.create(connection, checkfirst=True)
    elif inspector.has_table("player_identity_view"):
        columns = {
            column["name"] for column in inspector.get_columns("player_identity_view")
        }
        if "custom_alias" not in columns:
            connection.execute(
                text("ALTER TABLE player_identity_view ADD COLUMN custom_alias TEXT")
            )

    if inspector.has_table("tournament_summary_view"):
        columns = {
            column["name"]
            for column in inspector.get_columns("tournament_summary_view")
        }
        if "event_id" not in columns:
            connection.execute(
                text("ALTER TABLE tournament_summary_view ADD COLUMN event_id TEXT")
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_tournament_summary_view_event_id "
                    "ON tournament_summary_view (event_id)"
                )
            )

    if inspector.has_table("event_summary_view"):
        columns = {
            column["name"] for column in inspector.get_columns("event_summary_view")
        }
        if "start_date" not in columns:
            connection.execute(
                text("ALTER TABLE event_summary_view ADD COLUMN start_date TIMESTAMP")
            )
        if "end_date" not in columns:
            connection.execute(
                text("ALTER TABLE event_summary_view ADD COLUMN end_date TIMESTAMP")
            )

    if inspector.has_table("event_player_stats_view"):
        pk = inspector.get_pk_constraint("event_player_stats_view") or {}
        constrained = list(pk.get("constrained_columns") or [])
        if set(constrained) != {"event_id", "steam_id"}:
            connection.execute(text("DROP TABLE event_player_stats_view"))
            from .models import EventPlayerStatsProjection

            EventPlayerStatsProjection.__table__.create(connection, checkfirst=True)


async def get_read_session() -> AsyncGenerator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
