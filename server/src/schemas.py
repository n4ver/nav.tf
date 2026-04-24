"""Response and data schemas for API endpoints."""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List


class MedicStatResponse(BaseModel):
    ubers: int
    drops: int
    healing_done: int
    hpm: float


class LeaderboardEntryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    name: str
    steamid: str
    class_name: str = Field(alias="class")
    avg_rating: float
    avg_dpm: float
    avg_hpm: float
    avg_kad: float
    avg_kdr: float
    avg_kills: float
    avg_deaths: float
    avg_heals: float
    total_ubers: int
    total_drops: int
    playtime_mins: int


class LogStatEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    steamid: str
    player_name: Optional[str]
    class_name: str = Field(alias="class")
    kills: int
    deaths: int
    dpm: float
    medic: Optional[MedicStatResponse] = None


class LogStatsSummary(BaseModel):
    entries: int
    total_kills: int
    total_deaths: int
    avg_dpm: float


class LogStatsResponse(BaseModel):
    log_id: int
    match_id: int
    map: str
    tournament_id: int
    summary: LogStatsSummary
    stats: List[LogStatEntry]


class PlayerAggregateStats(BaseModel):
    matches_played: int
    avg_rating: float
    total_kills: int
    total_deaths: int
    total_playtime_mins: int
    avg_dpm: float
    avg_kdr: float
    total_damage_dealt: int
    total_damage_received: int
    total_heals_received: int


class PlayerMatchEntry(BaseModel):
    match_id: int
    log_id: int
    map: str
    tournament_id: int
    team: str
    playtime_mins: int
    kills: int
    deaths: int
    dpm: float
    damage_dealt: int
    damage_received: int
    heals_received: int
    total_ubers: int
    total_drops: int
    hpm: float
    rating: float


class PlayerSummaryResponse(BaseModel):
    steamid: str
    player_name: Optional[str]
    aggregate_stats: PlayerAggregateStats
    matches: List[PlayerMatchEntry]


class PlayerClassAggregateResponse(BaseModel):
    steamid: str
    player_name: Optional[str]
    class_id: int
    class_name: str
    aggregate_stats: PlayerAggregateStats


class JobStatus(BaseModel):
    job_id: int
    status: str
    detail: Optional[str] = None
    updated_at: str
