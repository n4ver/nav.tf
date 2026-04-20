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
    class_name: str = Field(alias="class")
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


class PlayerClassBreakdown(BaseModel):
    class_name: str
    avg_dpm: float
    sum_kills: int
    matches_played: int


class PlayerSummaryResponse(BaseModel):
    steamid: str
    ai_classification: str
    class_breakdown: List[PlayerClassBreakdown]


class JobStatus(BaseModel):
    job_id: int
    status: str
    detail: Optional[str] = None
    updated_at: str
