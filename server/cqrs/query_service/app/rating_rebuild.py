"""Debounced, coalesced rating rebuilds for the query read model.

Ratings are scored against benchmarks computed over *every* class row, so a new
match changes every rating. Instead of rebuilding inside each MatchParsed
handler (O(dataset) per event), handlers bump ``rating_rebuild_state.request_seq``
and this module runs one full rebuild per burst of events:

- ``deferred`` mode (default with RabbitMQ): a background worker polls the state
  row and rebuilds once events have been quiet for RATING_REBUILD_DEBOUNCE_MS, or
  RATING_REBUILD_MAX_DELAY_MS after the first pending request, whichever is first.
- ``inline`` mode (default with CQRS_BROKER_MODE=memory, used by tests and the
  in-process seed): the rebuild runs right after each event commits.

A Postgres advisory lock ensures one rebuild at a time across query replicas.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta

from sqlalchemy import text

from ...shared.timeutils import utcnow
from .db import SessionLocal
from .models import RatingRebuildState
from .services import ProjectionService

logger = logging.getLogger(__name__)

# Stable key for pg_try_advisory_xact_lock; scoped to the query database.
REBUILD_LOCK_KEY = 8_200_001


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def rebuild_mode() -> str:
    explicit = os.getenv("RATING_REBUILD_MODE", "").strip().lower()
    if explicit in {"inline", "deferred"}:
        return explicit
    if os.getenv("CQRS_BROKER_MODE", "").lower() == "memory":
        return "inline"
    return "deferred"


def debounce_delay() -> timedelta:
    return timedelta(milliseconds=max(_env_int("RATING_REBUILD_DEBOUNCE_MS", 2000), 0))


def max_delay() -> timedelta:
    return timedelta(
        milliseconds=max(_env_int("RATING_REBUILD_MAX_DELAY_MS", 30000), 0)
    )


def is_due(state: RatingRebuildState, now: datetime) -> bool:
    """True when pending work has been quiet long enough or waited too long."""
    if int(state.request_seq or 0) <= int(state.completed_seq or 0):
        return False
    last = state.last_requested_at or state.pending_since
    if last is None or now - last >= debounce_delay():
        return True
    return state.pending_since is not None and now - state.pending_since >= max_delay()


async def run_pending_rating_rebuild(
    *,
    force: bool = False,
    now: datetime | None = None,
    wait_for_lock: bool = False,
) -> bool:
    """Run one coalesced rebuild if work is pending (and due, unless forced).

    Returns True when a rebuild ran. Safe to call concurrently. By default a
    caller that does not get the advisory lock returns False immediately (the
    worker simply tries again on its next poll). With ``wait_for_lock=True`` it
    waits for the current run to finish and then re-checks for pending work;
    inline mode needs this because there is no worker to pick up a request that
    arrived after the running rebuild took its snapshot.
    """
    async with SessionLocal() as session:
        if wait_for_lock:
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": REBUILD_LOCK_KEY},
            )
        else:
            locked = (
                await session.execute(
                    text("SELECT pg_try_advisory_xact_lock(:key)"),
                    {"key": REBUILD_LOCK_KEY},
                )
            ).scalar_one()
            if not locked:
                await session.rollback()
                return False

        state = await session.get(RatingRebuildState, 1)
        current = now or utcnow()
        if state is None or int(state.request_seq or 0) <= int(
            state.completed_seq or 0
        ):
            await session.rollback()
            return False
        if not force and not is_due(state, current):
            await session.rollback()
            return False

        target_seq = int(state.request_seq)
        started_at = utcnow()
        service = ProjectionService(session)
        try:
            # Snapshot not-yet-rated matches *before* loading class rows: anything
            # committed after this point bumps request_seq and gets the next run.
            pending_match_ids = await service.pending_rating_match_ids()
            await service.rebuild_ratings()
            await service.mark_ratings_ready(pending_match_ids)
            # Every rating may have moved, so every leaderboard and event is stale.
            await service.refresh_all_tournament_leaderboards()
            await service.refresh_all_event_player_stats()
            finished_at = utcnow()
            await session.execute(
                text(
                    """
                    UPDATE rating_rebuild_state
                    SET completed_seq = GREATEST(completed_seq, :seq),
                        pending_since = CASE
                            WHEN request_seq <= :seq THEN NULL
                            ELSE CAST(:finished_at AS TIMESTAMP)
                        END,
                        last_run_started_at = :started_at,
                        last_run_finished_at = :finished_at,
                        last_error = NULL
                    WHERE id = 1
                    """
                ),
                {
                    "seq": target_seq,
                    "started_at": started_at,
                    "finished_at": finished_at,
                },
            )
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.exception("Rating rebuild failed (seq=%s)", target_seq)
            await _record_rebuild_error(repr(exc))
            raise

    logger.info(
        "Rating rebuild completed seq=%s matches_marked_ready=%s duration=%.2fs",
        target_seq,
        len(pending_match_ids),
        (finished_at - started_at).total_seconds(),
    )
    await _resolve_identities_best_effort()
    return True


async def _record_rebuild_error(error: str) -> None:
    try:
        async with SessionLocal() as session:
            await session.execute(
                text(
                    "UPDATE rating_rebuild_state "
                    "SET last_error = :error, last_run_finished_at = :now WHERE id = 1"
                ),
                {"error": error[:1000], "now": utcnow()},
            )
            await session.commit()
    except Exception:
        logger.exception("Could not record rating rebuild error")


async def _resolve_identities_best_effort() -> None:
    """Steam persona lookup runs after the rebuild commits, outside its transaction."""
    try:
        async with SessionLocal() as session:
            await ProjectionService(session).resolve_missing_player_identities()
            await session.commit()
    except Exception:
        logger.exception("Steam identity resolution failed; will retry next rebuild")


async def run_inline_rating_rebuild_if_enabled() -> None:
    if rebuild_mode() == "inline":
        await run_pending_rating_rebuild(force=True, wait_for_lock=True)


async def request_rebuild_if_unrated_matches() -> None:
    """Startup hook: queue a rebuild if matches are waiting for ratings.

    Covers upgrades from the inline-rebuild version and crashes mid-rebuild.
    """
    async with SessionLocal() as session:
        service = ProjectionService(session)
        if await service.pending_rating_match_ids(limit=1):
            await service.request_rating_rebuild()
            await session.commit()


class RatingRebuildWorker:
    def __init__(self, *, poll_interval_ms: int | None = None) -> None:
        self.poll_interval_ms = (
            poll_interval_ms
            if poll_interval_ms is not None
            else _env_int("RATING_REBUILD_POLL_MS", 1000)
        )
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopping = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="rating-rebuild")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        self._task = None

    async def _run(self) -> None:
        interval = max(self.poll_interval_ms, 100) / 1000.0
        logger.info("Rating rebuild worker started (interval=%.2fs)", interval)
        while not self._stopping.is_set():
            try:
                await run_pending_rating_rebuild()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                # Already logged with a traceback and recorded in last_error; the
                # request stays pending and the next poll retries it.
                logger.debug("Rating rebuild will be retried on the next poll")
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=interval)
            except TimeoutError:
                continue


RATING_REBUILD_WORKER = RatingRebuildWorker()


async def start_rating_rebuild_worker() -> None:
    await request_rebuild_if_unrated_matches()
    if rebuild_mode() == "deferred":
        RATING_REBUILD_WORKER.start()
    else:
        await run_pending_rating_rebuild(force=True, wait_for_lock=True)


async def stop_rating_rebuild_worker() -> None:
    await RATING_REBUILD_WORKER.stop()
