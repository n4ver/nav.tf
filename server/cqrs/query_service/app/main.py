from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from ...shared.broker import close_broker
from ...shared.cors import add_cors_middleware
from ...shared.schemas import (
    ClassRatingBenchmarkView,
    EventDetailView,
    EventSummaryView,
    LeaderboardEntryView,
    MatchSummaryView,
    PlayerLifetimeStatsView,
    SearchResultView,
    TournamentSummaryView,
)
from ...shared.settings import enforce_production_settings, fastapi_docs_kwargs
from .consumer import start_event_consumer
from .db import SessionLocal, get_read_session, init_read_db
from .models import MatchSummaryProjection
from .rating_rebuild import start_rating_rebuild_worker, stop_rating_rebuild_worker
from .services import ProjectionService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    enforce_production_settings("query")
    await init_read_db()
    logger.info("Query service database initialized")
    start_event_consumer()
    await start_rating_rebuild_worker()
    yield
    await stop_rating_rebuild_worker()
    await close_broker()


app = FastAPI(
    title="CQRS Query Service",
    version="1.0.0",
    lifespan=lifespan,
    **fastapi_docs_kwargs(),
)
add_cors_middleware(app)


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    logger.exception("Unhandled query service error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/api/v1/queries/matches", response_model=list[MatchSummaryView])
async def list_matches(
    skip: int = 0,
    limit: int = 20,
    tournament_id: str | None = None,
    event_id: str | None = None,
    session: AsyncSession = Depends(get_read_session),
) -> list[MatchSummaryView]:
    service = ProjectionService(session)
    return await service.list_matches(
        skip=skip,
        limit=min(limit, 100),
        tournament_id=tournament_id,
        event_id=event_id,
    )


@app.get("/api/v1/queries/matches/{match_id}")
async def get_match(
    match_id: str,
    session: AsyncSession = Depends(get_read_session),
) -> dict:
    service = ProjectionService(session)
    match = await service.get_match(match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    return match


@app.get("/api/v1/queries/tournaments", response_model=list[TournamentSummaryView])
async def list_tournaments(
    session: AsyncSession = Depends(get_read_session),
) -> list[TournamentSummaryView]:
    service = ProjectionService(session)
    return await service.list_tournaments()


@app.get(
    "/api/v1/queries/tournaments/{tournament_id}/leaderboard",
    response_model=list[LeaderboardEntryView],
)
async def get_tournament_leaderboard(
    tournament_id: str,
    class_name: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_read_session),
) -> list[LeaderboardEntryView]:
    service = ProjectionService(session)
    return await service.get_tournament_leaderboard(
        tournament_id=tournament_id,
        class_name=class_name,
        limit=limit,
    )


@app.get("/api/v1/queries/leaderboard", response_model=list[LeaderboardEntryView])
async def get_global_leaderboard(
    class_name: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_read_session),
) -> list[LeaderboardEntryView]:
    service = ProjectionService(session)
    return await service.get_global_leaderboard(class_name=class_name, limit=limit)


@app.get("/api/v1/queries/events", response_model=list[EventSummaryView])
async def list_events(
    session: AsyncSession = Depends(get_read_session),
) -> list[EventSummaryView]:
    service = ProjectionService(session)
    return await service.list_events()


@app.get("/api/v1/queries/events/{event_id}", response_model=EventDetailView)
async def get_event(
    event_id: str,
    session: AsyncSession = Depends(get_read_session),
) -> EventDetailView:
    service = ProjectionService(session)
    event = await service.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.get(
    "/api/v1/queries/events/{event_id}/leaderboard",
    response_model=list[LeaderboardEntryView],
)
async def get_event_leaderboard(
    event_id: str,
    class_name: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_read_session),
) -> list[LeaderboardEntryView]:
    service = ProjectionService(session)
    event = await service.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return await service.get_event_leaderboard(
        event_id=event_id,
        class_name=class_name,
        limit=limit,
    )


@app.get(
    "/api/v1/queries/players/{steam_id}/stats", response_model=PlayerLifetimeStatsView
)
async def get_player_stats(
    steam_id: str,
    session: AsyncSession = Depends(get_read_session),
) -> PlayerLifetimeStatsView:
    service = ProjectionService(session)
    return await service.get_player_stats(steam_id)


@app.get("/api/v1/queries/search", response_model=list[SearchResultView])
async def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=50),
    session: AsyncSession = Depends(get_read_session),
) -> list[SearchResultView]:
    service = ProjectionService(session)
    return await service.search(q, limit=limit)


@app.get(
    "/api/v1/queries/benchmarks/class-rating",
    response_model=list[ClassRatingBenchmarkView],
)
async def list_class_benchmarks(
    session: AsyncSession = Depends(get_read_session),
) -> list[ClassRatingBenchmarkView]:
    service = ProjectionService(session)
    return await service.list_benchmarks()


@app.get("/health")
async def health() -> dict[str, object]:
    match_count = 0
    db_reachable = False
    try:
        async with SessionLocal() as session:
            match_count = (
                await session.execute(
                    select(func.count()).select_from(MatchSummaryProjection)
                )
            ).scalar_one()
        db_reachable = True
    except Exception as exc:  # noqa: BLE001 — surface connectivity in health payload
        logger.warning("Query health DB check failed: %s", exc)

    return {
        "status": "ok" if db_reachable else "degraded",
        "side": "query",
        "db_reachable": db_reachable,
        "match_count": match_count,
        "repair_hint": None
        if db_reachable
        else "Check Postgres connectivity, then run: python seed/seed_cqrs.py --http --reset",
    }
