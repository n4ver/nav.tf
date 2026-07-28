"""Read-optimized materialized view tables for the query service."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, JSON, UniqueConstraint
from sqlmodel import Field

from ...shared.timeutils import utcnow
from .db import QuerySQLModel


class MatchSummaryProjection(QuerySQLModel, table=True):
    __tablename__ = "match_summary_view"

    match_id: str = Field(primary_key=True, index=True)
    tournament_id: str | None = Field(default=None, index=True)
    source_log_id: int | None = Field(default=None, index=True)
    map_name: str = Field(index=True)
    duration_seconds: int
    winning_team: str
    date_played: datetime = Field(default_factory=utcnow, index=True)
    blu_score: int = 0
    red_score: int = 0
    ratings_ready: bool = False


class TournamentSummaryProjection(QuerySQLModel, table=True):
    __tablename__ = "tournament_summary_view"

    tournament_id: str = Field(primary_key=True)
    name: str
    slug: str = Field(index=True)
    match_count: int = 0
    started_at: datetime | None = None


class PlayerMatchStatsProjection(QuerySQLModel, table=True):
    """Aggregated per-player match row for match detail UI."""

    __tablename__ = "player_match_stats_view"

    id: int | None = Field(default=None, primary_key=True)
    steam_id: str = Field(index=True)
    match_id: str = Field(index=True)
    team: str
    classes_played: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    primary_class: str = Field(default="unknown", index=True)
    playtime_seconds: int = 0
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    damage_per_minute: float = 0.0
    healing_done: int = 0
    rating: float = 1.0


class PlayerMatchClassStatsProjection(QuerySQLModel, table=True):
    """Per-class MatchStat-equivalent rating projection (RatingProjection).

    Holds the raw historical fields required by the full RatingService and the
    scored rating after benchmark rebuild.
    """

    __tablename__ = "player_match_class_stats_view"
    __table_args__ = (
        UniqueConstraint("steam_id", "match_id", "class_id", name="uq_player_match_class"),
    )

    id: int | None = Field(default=None, primary_key=True)
    steam_id: str = Field(index=True)
    match_id: str = Field(index=True)
    tournament_id: str | None = Field(default=None, index=True)
    team: str = "unknown"
    class_name: str = Field(index=True)
    class_id: int = Field(index=True)
    playtime_seconds: int = 0
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    dpm: float = 0.0
    primary_accuracy: float = 0.0
    damage_dealt: int = 0
    damage_received: int = 0
    heals_received: int = 0
    captures: int = 0
    headshots: int = 0
    backstabs: int = 0
    airshots: int = 0
    ubers: int = 0
    drops: int = 0
    healing_done: int = 0
    rating: float = 1.0


class PlayerLifetimeStatsProjection(QuerySQLModel, table=True):
    __tablename__ = "player_lifetime_stats_view"

    steam_id: str = Field(primary_key=True, index=True)
    matches_played: int = 0
    total_kills: int = 0
    total_deaths: int = 0
    total_assists: int = 0
    average_damage_per_minute: float = 0.0
    total_healing_done: int = 0
    average_rating: float = 1.0


class PlayerClassStatsProjection(QuerySQLModel, table=True):
    __tablename__ = "player_class_stats_view"

    id: int | None = Field(default=None, primary_key=True)
    steam_id: str = Field(index=True)
    class_name: str = Field(index=True)
    matches_played: int = 0
    total_kills: int = 0
    total_deaths: int = 0
    total_assists: int = 0
    average_damage_per_minute: float = 0.0
    total_healing_done: int = 0
    average_rating: float = 1.0


class ClassRatingBenchmarkProjection(QuerySQLModel, table=True):
    """Persisted class baselines used for request-free z-score scoring."""

    __tablename__ = "class_rating_benchmark_view"

    class_id: int = Field(primary_key=True)
    class_name: str = Field(index=True)
    sample_size: int = 0
    raw_p05: float = 0.0
    raw_p95: float = 1.0
    avg_rating: float = 1.0
    std_rating: float = 0.0
    min_rating: float = 0.0
    max_rating: float = 2.0
    p10_rating: float = 0.0
    p25_rating: float = 0.0
    p50_rating: float = 0.0
    p75_rating: float = 0.0
    p90_rating: float = 0.0
    metric_means: dict = Field(default_factory=dict, sa_column=Column(JSON))
    metric_stds: dict = Field(default_factory=dict, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=utcnow)


class PlayerIdentityProjection(QuerySQLModel, table=True):
    """Cached Steam persona / display name for a steam_id."""

    __tablename__ = "player_identity_view"

    steam_id: str = Field(primary_key=True, index=True)
    steam_id64: str | None = Field(default=None, index=True)
    persona_name: str | None = None
    custom_alias: str | None = None
    avatar_url: str | None = None
    resolved_at: datetime | None = None
    resolve_failed: bool = False


class LeaderboardSnapshotProjection(QuerySQLModel, table=True):
    """Precomputed tournament leaderboard rows (all-classes and per-class)."""

    __tablename__ = "leaderboard_snapshot_view"
    __table_args__ = (
        UniqueConstraint(
            "tournament_id",
            "steam_id",
            "class_name",
            name="uq_leaderboard_snapshot_tournament_player_class",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    tournament_id: str = Field(index=True)
    steam_id: str = Field(index=True)
    class_name: str = Field(default="", index=True)  # "" = all-classes aggregate
    matches_played: int = 0
    total_kills: int = 0
    total_deaths: int = 0
    total_assists: int = 0
    average_damage_per_minute: float = 0.0
    total_healing_done: int = 0
    average_rating: float = 1.0
    primary_class: str = "unknown"
    updated_at: datetime = Field(default_factory=utcnow)
