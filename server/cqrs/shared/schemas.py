"""API / domain DTOs shared as contracts across the CQRS boundary.

Command services may emit these shapes inside events.
Query services may return the view DTOs from read models.
Persistence tables live only in each service's own package.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .timeutils import utcnow


class RawLogUpload(BaseModel):
    log_data: str
    timestamp: datetime = Field(default_factory=utcnow)


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


class ClassStatSnapshot(BaseModel):
    """Per-class MatchStat-equivalent payload carried inside MatchParsed.

    Mirrors the monolith MatchStat (+ optional MedicStat) fields required by RatingService.
    Player-level dt/hr/ubers/drops/heal are applied onto class rows the same way the
    legacy ingest path does.
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
    captures: int = 0
    headshots: int = 0
    backstabs: int = 0
    airshots: int = 0
    ubers: int = 0
    drops: int = 0
    healing_done: int = 0


class PlayerStatSnapshot(BaseModel):
    """Per-player stats extracted on the write side and carried in MatchParsed."""

    steam_id: str
    team: str
    display_name: Optional[str] = None
    classes_played: List[str] = Field(default_factory=list)
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
    class_stats: List[ClassStatSnapshot] = Field(default_factory=list)


class MatchCommandModel(BaseModel):
    match_id: UUID = Field(default_factory=uuid4)
    map_name: str
    blu_score: int
    red_score: int
    duration_seconds: int = 1800
    players: List[PlayerStatSnapshot] = Field(default_factory=list)


class TournamentCommandModel(BaseModel):
    tournament_id: UUID = Field(default_factory=uuid4)
    name: str
    slug: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class UpdatePlayerDisplayNameCommand(BaseModel):
    steam_id: str
    display_name: str = Field(min_length=1, max_length=128)


class CreateTournamentCommand(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=1, max_length=128)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class UpdateTournamentCommand(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    slug: Optional[str] = Field(default=None, min_length=1, max_length=128)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class AuthUserView(BaseModel):
    steam_id: str
    display_name: str
    avatar_url: Optional[str] = None
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
    date_played: datetime
    ratings_ready: bool = False


class TournamentSummaryView(BaseModel):
    tournament_id: UUID
    name: str
    slug: str
    match_count: int
    started_at: Optional[datetime] = None


class PlayerStatsView(BaseModel):
    steam_id: str
    match_id: UUID
    team: str
    display_name: Optional[str] = None
    classes_played: List[str]
    primary_class: str = "unknown"
    playtime_seconds: int = 0
    kills: int
    deaths: int
    assists: int
    damage_per_minute: float
    healing_done: int
    rating: float = 1.0


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
    classes_played: List[str] = Field(default_factory=list)
    kills: int
    deaths: int
    assists: int
    damage_per_minute: float
    healing_done: int = 0
    rating: float = 1.0


class PlayerLifetimeStatsView(BaseModel):
    steam_id: str
    display_name: Optional[str] = None
    matches_played: int
    total_kills: int
    total_deaths: int
    total_assists: int
    average_damage_per_minute: float
    total_healing_done: int
    average_rating: float = 1.0
    class_breakdown: List[PlayerClassAggregateView] = Field(default_factory=list)
    recent_matches: List[PlayerRecentMatchView] = Field(default_factory=list)


class LeaderboardEntryView(BaseModel):
    steam_id: str
    display_name: Optional[str] = None
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
    display_name: Optional[str] = None
    source_log_id: int | None = None
