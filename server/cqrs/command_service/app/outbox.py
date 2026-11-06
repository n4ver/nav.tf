"""Transactional outbox: stage events with domain writes, relay to RabbitMQ.

Relay guarantees:

- **Single relayer.** A Postgres advisory lock serialises relays across the
  background worker, post-commit kicks and command-service replicas.
- **Publish order = commit order.** Rows are relayed by ``id``. When the head row
  fails (or is still backing off) the batch stops, so later events never overtake
  it. Consumers can rely on, say, MatchParsed arriving before a
  MatchTournamentAssigned for the same match.
- **Backoff, then park.** Failed publishes retry with exponential backoff
  (OUTBOX_RETRY_BASE_MS doubling up to OUTBOX_RETRY_MAX_MS). After
  OUTBOX_MAX_ATTEMPTS the row is marked FAILED so it stops blocking the queue;
  ``requeue_failed_events`` puts FAILED rows back once the cause is fixed.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import timedelta
from uuid import UUID

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from ...shared.broker import publish_event, retry_delay_seconds
from ...shared.events import EventEnvelope
from ...shared.timeutils import utcnow
from .models import OutboxEvent, OutboxStatus

logger = logging.getLogger(__name__)

# Stable key for pg_advisory_xact_lock; scoped to the command database.
RELAY_LOCK_KEY = 8_100_001


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _max_attempts() -> int:
    return max(_env_int("OUTBOX_MAX_ATTEMPTS", 15), 1)


def _retry_delay(attempts: int) -> timedelta:
    seconds = retry_delay_seconds(
        attempts,
        base_ms=_env_int("OUTBOX_RETRY_BASE_MS", 1000),
        max_ms=_env_int("OUTBOX_RETRY_MAX_MS", 300_000),
    )
    return timedelta(seconds=seconds)


async def stage_event(session: AsyncSession, envelope: EventEnvelope) -> None:
    """Add an outbox row to the current transaction (caller commits)."""
    session.add(
        OutboxEvent(
            event_id=envelope.event_id
            if isinstance(envelope.event_id, UUID)
            else UUID(str(envelope.event_id)),
            event_type=envelope.event_type,
            payload=envelope.model_dump_json(),
            status=OutboxStatus.PENDING,
        )
    )


async def _acquire_relay_lock(session: AsyncSession, *, wait: bool) -> bool:
    if wait:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": RELAY_LOCK_KEY}
        )
        return True
    return bool(
        (
            await session.execute(
                text("SELECT pg_try_advisory_xact_lock(:key)"),
                {"key": RELAY_LOCK_KEY},
            )
        ).scalar_one()
    )


async def relay_pending_events(
    session: AsyncSession,
    *,
    batch_size: int = 50,
    wait_for_lock: bool = True,
) -> int:
    """Publish pending outbox rows in order and mark them published.

    With ``wait_for_lock=False`` the call returns 0 immediately if another relay
    holds the lock (used by the background worker so it never queues up).
    """
    if not await _acquire_relay_lock(session, wait=wait_for_lock):
        await session.rollback()
        return 0

    rows = (
        (
            await session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.status == OutboxStatus.PENDING)
                .order_by(col(OutboxEvent.id))
                .limit(batch_size)
            )
        )
        .scalars()
        .all()
    )

    now = utcnow()
    published = 0
    for row in rows:
        if row.next_attempt_at is not None and row.next_attempt_at > now:
            # Head of the queue is still backing off; keep later events behind it.
            break

        try:
            envelope = json.loads(row.payload)
        except (TypeError, ValueError) as exc:
            # A corrupt payload can never be published; park it without retries.
            row.attempts = int(row.attempts or 0) + 1
            row.status = OutboxStatus.FAILED
            row.last_error = f"unreadable payload: {exc!r}"[:1000]
            logger.error("Outbox event_id=%s has an unreadable payload", row.event_id)
            continue

        try:
            await publish_event(row.event_type, envelope)
        except Exception as exc:  # noqa: BLE001
            row.attempts = int(row.attempts or 0) + 1
            row.last_error = str(exc)[:1000]
            if row.attempts >= _max_attempts():
                row.status = OutboxStatus.FAILED
                row.next_attempt_at = None
                logger.error(
                    "Outbox event_id=%s type=%s failed permanently after %s attempts: %s",
                    row.event_id,
                    row.event_type,
                    row.attempts,
                    exc,
                )
                # Parked: stop it blocking the rest of the queue.
                continue
            row.next_attempt_at = now + _retry_delay(row.attempts)
            logger.warning(
                "Outbox publish failed event_id=%s type=%s attempt=%s, retry at %s: %s",
                row.event_id,
                row.event_type,
                row.attempts,
                row.next_attempt_at.isoformat(),
                exc,
            )
            break

        row.status = OutboxStatus.PUBLISHED
        row.published_at = utcnow()
        row.next_attempt_at = None
        row.last_error = None
        published += 1

    await session.commit()
    return published


async def flush_outbox(*, wait_for_lock: bool = True) -> int:
    """Open a short-lived session and relay pending events (post-commit kick)."""
    from .db import SessionLocal

    async with SessionLocal() as session:
        return await relay_pending_events(session, wait_for_lock=wait_for_lock)


async def requeue_failed_events(
    session: AsyncSession, event_ids: list[UUID] | None = None
) -> int:
    """Move FAILED rows back to PENDING with a fresh retry budget.

    Requeued rows keep their original ``id``, so they publish ahead of any newer
    pending events, restoring the original order as far as possible.
    """
    stmt = (
        update(OutboxEvent)
        .where(col(OutboxEvent.status) == OutboxStatus.FAILED)
        .values(
            status=OutboxStatus.PENDING,
            attempts=0,
            next_attempt_at=None,
            last_error=None,
        )
    )
    if event_ids:
        stmt = stmt.where(col(OutboxEvent.event_id).in_(event_ids))
    result = await session.execute(stmt)
    await session.commit()
    return int(result.rowcount or 0)


async def outbox_status_counts(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.execute(
            text("SELECT status, count(*) FROM outbox_events GROUP BY status")
        )
    ).all()
    counts = {status.value: 0 for status in OutboxStatus}
    for status, count in rows:
        counts[str(status).lower()] = int(count)
    return counts
