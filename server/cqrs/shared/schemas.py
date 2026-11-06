"""API / domain DTOs shared as contracts across the CQRS boundary.

Command services may emit these shapes inside events.
Query services may return the view DTOs from read models.
Persistence tables live only in each service's own package.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .timeutils import utcnow


class RawLogUpload(BaseModel):
    log_data: str
    timestamp: datetime = Field(default_factory=utcnow)
    tournament_id: UUID | None = None


class CachedLogIngest(BaseModel):
    """Seed/import request. Payload is loaded server-side from SEED_CACHE_PATH when omitted."""

    log_id: int
    tournament_id: int
    section: str = "unknown"
    data: dict[str, Any] | None = None
    timestamp: datetime = Field(default_factory=utcnow)


class IngestLogsTfCommand(BaseModel):
    """Admin command: fetch a log live from the logs.tf API by ID."""

    logstf_id: int = Field(gt=0)
    tournament_id: UUID | None = None


class ClassStatSnapshot(BaseModel):
    """Per-class MatchStat-equivalent payload carried inside MatchParsed.

    Mirrors the monolith MatchStat (+ optional MedicStat) fields required by RatingService.
    Player-level dt/hr/heal are applied onto class rows the same way the legacy ingest
    path does. Player-level captures/headshots/backstabs/airshots and medic
    ubers/drops live on PlayerStatSnapshot instead.
    """

    class_name: str
    class_id: int
    playtime_seconds: int = 0
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    dpm: float = 0.0
    primary_accuracy: float = 0.0
    damage_dealt: int = 0
    damage_received: int = 0
    heals_received: int = 0
    healing_done: int = 0


class PlayerStatSnapshot(BaseModel):
    """Per-player stats extracted on the write side and carried in MatchParsed."""

    steam_id: str
    team: str
    display_name: str | None = None
    classes_played: list[str] = Field(default_factory=list)
    primary_class: str = "unknown"
    playtime_seconds: int = 0
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    damage_per_minute: float = 0.0
    healing_done: int = 0
    damage_received: int = 0
    heals_received: int = 0
    ubers: int = 0
    drops: int = 0
    captures: int = 0
    headshots: int = 0
    backstabs: int = 0
    airshots: int = 0
    class_stats: list[ClassStatSnapshot] = Field(default_factory=list)


class MatchCommandModel(BaseModel):
    match_id: UUID = Field(default_factory=uuid4)
    map_name: str
    blu_score: int
    red_score: int
    duration_seconds: int = 1800
    players: list[PlayerStatSnapshot] = Field(default_factory=list)


class TournamentCommandModel(BaseModel):
    tournament_id: UUID = Field(default_factory=uuid4)
    name: str
    slug: str
    start_date: datetime | None = None
    end_date: datetime | None = None
    event_id: UUID | None = None


class EventCommandModel(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    name: str
    slug: str
    start_date: datetime | None = None
    end_date: datetime | None = None


class UpdatePlayerDisplayNameCommand(BaseModel):
    steam_id: str
    display_name: str = Field(min_length=1, max_length=128)


class CreateTournamentCommand(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=1, max_length=128)
    start_date: datetime | None = None
    end_date: datetime | None = None
    event_id: UUID | None = None


class UpdateTournamentCommand(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    slug: str | None = Field(default=None, min_length=1, max_length=128)
    start_date: datetime | None = None
    end_date: datetime | None = None
    event_id: UUID | None = None


class CreateEventCommand(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=1, max_length=128)
    start_date: datetime | None = None
    end_date: datetime | None = None


class UpdateEventCommand(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    slug: str | None = Field(default=None, min_length=1, max_length=128)
    start_date: datetime | None = None
    end_date: datetime | None = None


class LinkTournamentToEventCommand(BaseModel):
    """Link a tournament to an event. Null event_id unlinks without deleting."""

    event_id: UUID | None = None


class AssignMatchTournamentCommand(BaseModel):
    tournament_id: UUID


class AuthUserView(BaseModel):
    steam_id: str
    display_name: str
    avatar_url: str | None = None
    role: str


class AuthCodeExchangeRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=256)


class AuthTokenResponse(BaseModel):
    token: str


class MatchSummaryView(BaseModel):
    match_id: UUID
    tournament_id: UUID | None = None
    source_log_id: int | None = None
    map_name: str
    duration_seconds: int
    winning_team: str
    blu_score: int = 0
    red_score: int = 0
    date_played: datetime
    ratings_ready: bool = False


class TournamentSummaryView(BaseModel):
    tournament_id: UUID
    name: str
    slug: str
    match_count: int
    started_at: datetime | None = None
    event_id: UUID | None = None


class EventSummaryView(BaseModel):
    event_id: UUID
    name: str
    slug: str
    start_date: datetime | None = None
    end_date: datetime | None = None
    tournament_ids: list[UUID] = Field(default_factory=list)
    tournament_count: int = 0
    match_count: int = 0


class EventDetailView(BaseModel):
    event: EventSummaryView
    tournaments: list[TournamentSummaryView] = Field(default_factory=list)


class ClassStatView(BaseModel):
    """Per-class Match CDM row returned on match detail (ClassStatSnapshot + rating)."""

    class_name: str
    class_id: int = 0
    playtime_seconds: int = 0
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    dpm: float = 0.0
    primary_accuracy: float = 0.0
    damage_dealt: int = 0
    damage_received: int = 0
    heals_received: int = 0
    healing_done: int = 0
    rating: float = 1.0


class PlayerStatsView(BaseModel):
    """Per-player Match CDM row for match detail (PlayerStatSnapshot + rating)."""

    steam_id: str
    match_id: UUID
    team: str
    display_name: str | None = None
    classes_played: list[str]
    primary_class: str = "unknown"
    playtime_seconds: int = 0
    kills: int
    deaths: int
    assists: int
    damage_per_minute: float
    healing_done: int
    damage_received: int = 0
    heals_received: int = 0
    ubers: int = 0
    drops: int = 0
    captures: int = 0
    headshots: int = 0
    backstabs: int = 0
    airshots: int = 0
    rating: float = 1.0
    class_stats: list[ClassStatView] = Field(default_factory=list)


class PlayerClassAggregateView(BaseModel):
    class_name: str
    matches_played: int
    total_kills: int
    total_deaths: int
    total_assists: int
    average_damage_per_minute: float
    total_healing_done: int
    average_rating: float


class PlayerRecentMatchView(BaseModel):
    match_id: UUID
    map_name: str
    date_played: datetime
    team: str
    classes_played: list[str] = Field(default_factory=list)
    kills: int
    deaths: int
    assists: int
    damage_per_minute: float
    healing_done: int = 0
    rating: float = 1.0


class PlayerLifetimeStatsView(BaseModel):
    steam_id: str
    display_name: str | None = None
    matches_played: int
    total_kills: int
    total_deaths: int
    total_assists: int
    average_damage_per_minute: float
    total_healing_done: int
    average_rating: float = 1.0
    class_breakdown: list[PlayerClassAggregateView] = Field(default_factory=list)
    recent_matches: list[PlayerRecentMatchView] = Field(default_factory=list)


class LeaderboardEntryView(BaseModel):
    steam_id: str
    display_name: str | None = None
    matches_played: int
    total_kills: int
    total_deaths: int
    total_assists: int
    average_damage_per_minute: float
    total_healing_done: int
    average_rating: float
    primary_class: str = "unknown"


class ClassRatingBenchmarkView(BaseModel):
    class_name: str
    class_id: int
    sample_size: int
    avg_rating: float
    std_rating: float = 0.0
    min_rating: float
    max_rating: float
    p50_rating: float = 1.0


class SearchResultView(BaseModel):
    kind: str
    id: str
    label: str
    match_id: UUID | None = None
    steam_id: str | None = None
    display_name: str | None = None
    source_log_id: int | None = None
