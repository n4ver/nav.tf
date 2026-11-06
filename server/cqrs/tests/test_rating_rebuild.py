"""Debounced rating rebuild, consumer idempotency and dependency checks."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from cqrs.query_service.app import rating_rebuild
from cqrs.query_service.app.db import SessionLocal
from cqrs.query_service.app.idempotency import handle_integration_event_idempotent
from cqrs.query_service.app.models import (
    MatchSummaryProjection,
    PlayerMatchStatsProjection,
    RatingRebuildState,
)
from cqrs.query_service.app.rating_rebuild import (
    REBUILD_LOCK_KEY,
    RatingRebuildWorker,
    is_due,
    request_rebuild_if_unrated_matches,
    run_pending_rating_rebuild,
)
from cqrs.query_service.app.services import ProjectionService
from cqrs.shared.events import MatchParsedEvent
from cqrs.shared.timeutils import utcnow


def _match_envelope(match_id: str, *, steam_id: str = "[U:1:100]") -> dict:
    return MatchParsedEvent(
        payload={
            "match_id": match_id,
            "map_name": "cp_process_final",
            "blu_score": 5,
            "red_score": 2,
            "duration_seconds": 1800,
            "date_played": "2024-01-01T12:00:00",
            "tournament": {
                "tournament_id": "default-tournament",
                "name": "Default",
                "slug": "default-tournament",
            },
            "players": [
                {
                    "steam_id": steam_id,
                    "team": "Blue",
                    "classes_played": ["scout"],
                    "primary_class": "scout",
                    "kills": 10,
                    "deaths": 5,
                    "assists": 3,
                    "damage_per_minute": 300,
                    "playtime_seconds": 1800,
                }
            ],
        },
    ).model_dump(mode="json")


async def _state() -> RatingRebuildState | None:
    async with SessionLocal() as session:
        return await session.get(RatingRebuildState, 1)


async def _ratings_ready(match_id: str) -> bool:
    async with SessionLocal() as session:
        row = await session.get(MatchSummaryProjection, match_id)
        assert row is not None
        return bool(row.ratings_ready)


@pytest.fixture
def deferred(monkeypatch, clean_dbs):
    monkeypatch.setenv("RATING_REBUILD_MODE", "deferred")
    monkeypatch.setenv("RATING_REBUILD_DEBOUNCE_MS", "60000")
    monkeypatch.setenv("RATING_REBUILD_MAX_DELAY_MS", "600000")


# --- scheduling logic ---------------------------------------------------------


def test_is_due_respects_debounce_and_max_delay(monkeypatch):
    monkeypatch.setenv("RATING_REBUILD_DEBOUNCE_MS", "2000")
    monkeypatch.setenv("RATING_REBUILD_MAX_DELAY_MS", "30000")
    now = utcnow()

    clean = RatingRebuildState(request_seq=3, completed_seq=3)
    assert is_due(clean, now) is False

    quiet = RatingRebuildState(
        request_seq=4,
        completed_seq=3,
        pending_since=now - timedelta(seconds=5),
        last_requested_at=now - timedelta(seconds=3),
    )
    assert is_due(quiet, now) is True

    busy = RatingRebuildState(
        request_seq=9,
        completed_seq=3,
        pending_since=now - timedelta(seconds=10),
        last_requested_at=now - timedelta(milliseconds=100),
    )
    assert is_due(busy, now) is False

    starving = RatingRebuildState(
        request_seq=90,
        completed_seq=3,
        pending_since=now - timedelta(seconds=31),
        last_requested_at=now - timedelta(milliseconds=100),
    )
    assert is_due(starving, now) is True


def test_rebuild_mode_defaults(monkeypatch):
    monkeypatch.delenv("RATING_REBUILD_MODE", raising=False)
    monkeypatch.setenv("CQRS_BROKER_MODE", "memory")
    assert rating_rebuild.rebuild_mode() == "inline"
    monkeypatch.setenv("CQRS_BROKER_MODE", "")
    assert rating_rebuild.rebuild_mode() == "deferred"
    monkeypatch.setenv("RATING_REBUILD_MODE", "inline")
    assert rating_rebuild.rebuild_mode() == "inline"


# --- deferred rebuild ---------------------------------------------------------


@pytest.mark.asyncio
async def test_match_parsed_defers_rating_work(deferred):
    match_id = str(uuid4())
    await handle_integration_event_idempotent("MatchParsed", _match_envelope(match_id))

    assert await _ratings_ready(match_id) is False
    state = await _state()
    assert state is not None
    assert state.request_seq == 1 and state.completed_seq == 0
    assert state.pending_since is not None

    # Not due yet (debounce is 60s), so an unforced run does nothing...
    assert await run_pending_rating_rebuild() is False
    # ...until the debounce window has passed.
    assert await run_pending_rating_rebuild(now=utcnow() + timedelta(minutes=2))
    assert await _ratings_ready(match_id) is True
    state = await _state()
    assert state.completed_seq == state.request_seq == 1
    assert state.pending_since is None
    assert state.last_error is None
    assert state.last_run_finished_at is not None

    # Nothing pending any more.
    assert await run_pending_rating_rebuild(force=True) is False


@pytest.mark.asyncio
async def test_burst_of_matches_is_rated_by_one_rebuild(deferred, monkeypatch):
    calls = {"n": 0}
    original = ProjectionService.rebuild_ratings

    async def counting(self):
        calls["n"] += 1
        return await original(self)

    monkeypatch.setattr(ProjectionService, "rebuild_ratings", counting)
    match_ids = [str(uuid4()) for _ in range(3)]
    for index, match_id in enumerate(match_ids):
        await handle_integration_event_idempotent(
            "MatchParsed", _match_envelope(match_id, steam_id=f"[U:1:{200 + index}]")
        )

    assert calls["n"] == 0
    assert (await _state()).request_seq == 3

    assert await run_pending_rating_rebuild(force=True) is True
    assert calls["n"] == 1
    for match_id in match_ids:
        assert await _ratings_ready(match_id) is True

    async with SessionLocal() as session:
        rows = (
            (await session.execute(PlayerMatchStatsProjection.__table__.select()))
            .mappings()
            .all()
        )
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_request_during_rebuild_keeps_work_pending(deferred, monkeypatch):
    first = str(uuid4())
    await handle_integration_event_idempotent("MatchParsed", _match_envelope(first))
    original = ProjectionService.rebuild_ratings

    async def with_concurrent_request(self):
        # Another event commits while the rebuild is running.
        async with SessionLocal() as other:
            await ProjectionService(other).request_rating_rebuild()
            await other.commit()
        return await original(self)

    monkeypatch.setattr(ProjectionService, "rebuild_ratings", with_concurrent_request)
    assert await run_pending_rating_rebuild(force=True) is True

    state = await _state()
    assert state.completed_seq == 1
    assert state.request_seq == 2
    # Still pending, with the debounce window restarted from the finished run.
    assert state.pending_since is not None
    assert await _ratings_ready(first) is True


@pytest.mark.asyncio
async def test_rebuild_skips_when_another_runner_holds_the_lock(deferred):
    await handle_integration_event_idempotent(
        "MatchParsed", _match_envelope(str(uuid4()))
    )
    async with SessionLocal() as holder:
        await holder.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": REBUILD_LOCK_KEY}
        )
        assert await run_pending_rating_rebuild(force=True) is False
        await holder.rollback()
    assert await run_pending_rating_rebuild(force=True) is True


@pytest.mark.asyncio
async def test_failed_rebuild_records_error_and_stays_pending(deferred, monkeypatch):
    match_id = str(uuid4())
    await handle_integration_event_idempotent("MatchParsed", _match_envelope(match_id))

    async def boom(self):
        raise RuntimeError("benchmark math exploded")

    original = ProjectionService.rebuild_ratings
    monkeypatch.setattr(ProjectionService, "rebuild_ratings", boom)
    with pytest.raises(RuntimeError):
        await run_pending_rating_rebuild(force=True)

    state = await _state()
    assert state.completed_seq == 0
    assert "benchmark math exploded" in (state.last_error or "")
    assert await _ratings_ready(match_id) is False

    monkeypatch.setattr(ProjectionService, "rebuild_ratings", original)
    assert await run_pending_rating_rebuild(force=True) is True
    assert (await _state()).last_error is None
    assert await _ratings_ready(match_id) is True


@pytest.mark.asyncio
async def test_startup_requests_rebuild_for_unrated_matches(deferred):
    async with SessionLocal() as session:
        session.add(
            MatchSummaryProjection(
                match_id="legacy-unrated",
                map_name="cp_gullywash_final1",
                duration_seconds=1800,
                winning_team="blu",
                ratings_ready=False,
            )
        )
        await session.commit()

    assert await _state() is None
    await request_rebuild_if_unrated_matches()
    state = await _state()
    assert state is not None and state.request_seq == 1

    assert await run_pending_rating_rebuild(force=True) is True
    assert await _ratings_ready("legacy-unrated") is True


@pytest.mark.asyncio
async def test_deferred_worker_runs_rebuild_in_background(deferred, monkeypatch):
    monkeypatch.setenv("RATING_REBUILD_DEBOUNCE_MS", "0")
    match_id = str(uuid4())
    await handle_integration_event_idempotent("MatchParsed", _match_envelope(match_id))

    worker = RatingRebuildWorker(poll_interval_ms=100)
    worker.start()
    try:
        for _ in range(50):
            if await _ratings_ready(match_id):
                break
            await asyncio.sleep(0.1)
    finally:
        await worker.stop()
    assert await _ratings_ready(match_id) is True


@pytest.mark.asyncio
async def test_inline_mode_rates_immediately(clean_dbs, monkeypatch):
    monkeypatch.setenv("RATING_REBUILD_MODE", "inline")
    match_id = str(uuid4())
    await handle_integration_event_idempotent("MatchParsed", _match_envelope(match_id))
    assert await _ratings_ready(match_id) is True


@pytest.mark.asyncio
async def test_inline_rebuild_waits_for_running_rebuild(clean_dbs, monkeypatch):
    """Inline mode has no worker, so a request must not be skipped on lock contention."""
    monkeypatch.setenv("RATING_REBUILD_MODE", "deferred")
    match_id = str(uuid4())
    await handle_integration_event_idempotent("MatchParsed", _match_envelope(match_id))

    async with SessionLocal() as holder:
        await holder.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": REBUILD_LOCK_KEY}
        )
        monkeypatch.setenv("RATING_REBUILD_MODE", "inline")
        inline = asyncio.create_task(
            rating_rebuild.run_inline_rating_rebuild_if_enabled()
        )
        await asyncio.sleep(0.3)
        assert not inline.done()  # blocked behind the "running" rebuild
        await holder.rollback()  # the other rebuild finishes and releases the lock

    await asyncio.wait_for(inline, timeout=10)
    assert await _ratings_ready(match_id) is True
