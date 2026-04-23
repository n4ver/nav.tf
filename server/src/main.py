"""TF2 Analytics API - FastAPI Backend"""

import asyncio
import httpx
import logging
import os
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

from models import Match, MatchStat, MedicStat, Player, Class
from models import seed_classes, get_or_create_tournament, get_or_create_player, get_class_id_from_name
from services import LeaderboardService, LogService, PlayerService

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///database.db")
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
LOGS_TF_API = "https://logs.tf/json"

# --- DATABASE SETUP ---
def _normalize_async_database_url(url: str) -> str:
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


engine = create_async_engine(_normalize_async_database_url(DATABASE_URL), echo=False)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

# In-memory status tracking for log ingestion jobs
JOB_STATUS: dict[int, dict] = {}


async def get_session():
    """Dependency: Get database session."""
    async with async_session_maker() as session:
        yield session


# --- APP SETUP ---
app = FastAPI(
    title="TF2 Analytics API",
    description="Competitive Team Fortress 2 analytics and leaderboard system",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/")
def root():
    return {"Hello": "World"}


# --- STARTUP/SHUTDOWN ---

@app.on_event("startup")
async def on_startup():
    """Initialize database and seed classes on startup."""
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    async with async_session_maker() as session:
        await seed_classes(session)
    logger.info("Database initialized and classes seeded.")


# --- LOG INGESTION BACKGROUND TASK ---

def _set_job_status(job_id: int, status: str, detail: Optional[str] = None):
    """Helper to update job status."""
    JOB_STATUS[job_id] = {
        "job_id": job_id,
        "status": status,
        "detail": detail,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def fetch_and_process_log(log_id: int, tournament_id: int):
    """Fetch log from logs.tf API and ingest into database."""
    _set_job_status(log_id, "processing")
    
    try:
        # Skip external fetch if this log is already ingested.
        async with async_session_maker() as db:
            result = await db.execute(select(Match).where(Match.log_id == log_id))
            existing_match = result.scalars().first()
            if existing_match:
                logger.info(f"Log {log_id} already ingested; skipping logs.tf fetch")
                _set_job_status(log_id, "completed", "Already ingested")
                return

        # Fetch log data from logs.tf
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{LOGS_TF_API}/{log_id}")
            if response.status_code != 200:
                logger.error(f"Failed to fetch log {log_id}: HTTP {response.status_code}")
                _set_job_status(log_id, "failed", f"HTTP {response.status_code}")
                return
            data = response.json()

        # Process log into database
        async with async_session_maker() as db:
            await _ingest_log_data(db, log_id, tournament_id, data)
        
        _set_job_status(log_id, "completed")
        logger.info(f"Successfully ingested log {log_id}")
        
    except Exception as exc:
        logger.exception(f"Error processing log {log_id}")
        _set_job_status(log_id, "failed", str(exc))
        raise


async def _ingest_log_data(db: AsyncSession, log_id: int, tournament_id: int, data: dict):
    """Ingest log data into database."""
    
    # Check if already ingested
    result = await db.execute(select(Match).where(Match.log_id == log_id))
    existing_match = result.scalars().first()
    if existing_match:
        logger.info(f"Log {log_id} already ingested")
        return

    tournament = await get_or_create_tournament(
        db,
        tournament_id,
        data.get("info", {}).get("title") or f"Tournament {tournament_id}",
    )

    # Create match entry
    new_match = Match(
        log_id=log_id,
        map=data["info"]["map"],
        tournament_id=tournament_id,
    )
    db.add(new_match)
    await db.flush()

    # Process players
    medicstats_dict = data.get("medicstats", {})
    
    for steam_id, p_data in data["players"].items():
        for c_stats in p_data.get("class_stats", []):
            player_id = await get_or_create_player(db, steam_id, data["names"].get(steam_id, "Unknown"))
            
            playtime = c_stats.get("total_time", 0)
            dpm = c_stats.get("dmg", 0) / (playtime / 60) if playtime > 0 else 0
            
            stat_entry = MatchStat(
                player_id=player_id,
                match_id=new_match.id,  # type: ignore
                class_id=get_class_id_from_name(c_stats["type"]),
                team=p_data.get("team", "Unknown"),
                playtime=playtime,
                kills=c_stats.get("kills", 0),
                deaths=c_stats.get("deaths", 0),
                dpm=dpm,
                primary_accuracy=c_stats.get("weapon", {}).get("primary", {}).get("acc", 0.0),
                damage_dealt=c_stats.get("dmg", 0),
                damage_received=p_data.get("dt", 0),
                heals_received=p_data.get("hr", 0),
                headshots=c_stats.get("headshots", 0),
                backstabs=c_stats.get("backstabs", 0),
                airshots=c_stats.get("as", 0),
                captures=c_stats.get("cpc", 0),
            )
            
            new_match.stats.append(stat_entry)
            db.add(stat_entry)
            await db.flush()

            # Create medic stats if applicable
            if c_stats["type"].lower() == "medic":
                healing_done = p_data.get("heal", 0)
                hpm = healing_done / (playtime / 60) if playtime > 0 else 0
                
                medic_stat = MedicStat(
                    matchstat_id=stat_entry.id,  # type: ignore
                    player_id=player_id,
                    ubers=p_data.get("ubers", 0),
                    drops=p_data.get("drops", 0),
                    healing_done=healing_done,
                    hpm=hpm,
                )
                db.add(medic_stat)

    await db.commit()




# --- API ENDPOINTS ---

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_session)):
    """Service health check endpoint."""
    try:
        await db.scalar(select(Class.id))
        return {"status": "ok"}
    except Exception as exc:
        logger.error(f"Health check failed: {exc}")
        raise HTTPException(status_code=500, detail="Database connection failed")


# --- LEADERBOARD ENDPOINTS ---

@app.get("/tournaments/{t_id}/leaderboard", tags=["leaderboard"])
async def get_tournament_leaderboard(
    t_id: int,
    class_name: str = Query(..., description="TF2 class name (e.g., Scout, Medic, Soldier)"),
    sort_by: Literal["rating", "dpm", "kad", "kills", "deaths", "playtime", "hpm", "ubers", "drops"] = Query(default="rating"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    min_playtime_seconds: int = Query(default=600, ge=600),
    limit: int = Query(default=10, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
):
    """Get leaderboard for a specific tournament and class with specialized Medic metrics."""
    try:
        # Build query
        statement, avg_hpm_expr, avg_dpm_expr, avg_kad_expr, avg_rating_expr, avg_deaths_expr, total_playtime_expr, total_ubers_expr, total_drops_expr = (
            LeaderboardService.build_leaderboard_query(
                db, t_id, class_name, min_playtime_seconds, limit
            )
        )
        
        # Apply sorting
        statement = LeaderboardService.apply_sorting(
            statement,
            class_name,
            sort_by,
            sort_order,
            avg_hpm_expr,
            avg_dpm_expr,
            avg_kad_expr,
            avg_rating_expr,
            None,
            avg_deaths_expr,
            total_playtime_expr,
            total_ubers_expr,
            total_drops_expr,
        )
        
        # Execute and transform
        results = (await db.execute(statement)).all()
        return [LeaderboardService.transform_leaderboard_result(r) for r in results]
    except Exception as exc:
        logger.error(f"Leaderboard query failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch leaderboard")


@app.get("/tournaments/{t_id}/matches", tags=["matches"])
async def list_tournament_matches(
    t_id: int,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_session),
):
    """List all matches for a specific tournament."""
    try:
        statement = (
            select(Match)
            .where(Match.tournament_id == t_id)
            .offset(offset)
            .limit(limit)
        )
        return (await db.execute(statement)).scalars().all()
    except Exception as exc:
        logger.error(f"Failed to list matches: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch matches")


@app.get("/matches", tags=["matches"])
async def list_all_matches(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
):
    """List all matches in the database with pagination metadata."""
    try:
        statement = (
            select(Match)
            .offset(offset)
            .limit(limit)
        )
        total_count = int((await db.scalar(select(func.count()).select_from(Match))) or 0)
        matches = (await db.execute(statement)).scalars().all()
        return {
            "items": matches,
            "total": total_count,
            "limit": limit,
            "offset": offset,
        }
    except Exception as exc:
        logger.error(f"Failed to list all matches: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch matches")


# --- LOG ENDPOINTS ---

@app.post("/logs/ingest/{log_id}", tags=["logs"])
async def ingest_log(
    log_id: int,
    tournament_id: int,
    background_tasks: BackgroundTasks,
):
    """Queue a log for ingestion from logs.tf."""
    _set_job_status(log_id, "queued")
    background_tasks.add_task(fetch_and_process_log, log_id, tournament_id)
    await asyncio.sleep(0.1)
    return {
        "message": f"Ingestion for log {log_id} started.",
        "job_id": log_id,
    }


@app.get("/logs/status/{job_id}", tags=["logs"])
def get_log_job_status(job_id: int):
    """Get the status of a log ingestion job."""
    status = JOB_STATUS.get(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return status


@app.get("/logs/{log_id}/stats", tags=["logs"])
async def get_log_stats(log_id: int, db: AsyncSession = Depends(get_session)):
    """Get all statistics for a specific log."""
    try:
        return await LogService.get_log_stats(db, log_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Failed to fetch log stats: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch log statistics")


# --- PLAYER ENDPOINTS ---

@app.get("/players/{steam_id}/summary", tags=["players"])
async def get_player_summary(steam_id: str, db: AsyncSession = Depends(get_session)):
    """Get aggregate stats for a specific player across all matches."""
    try:
        return await PlayerService.get_player_summary(db, steam_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Failed to fetch player summary: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch player summary")

