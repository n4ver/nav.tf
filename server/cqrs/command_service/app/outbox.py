"""Transactional outbox: stage events with domain writes, relay to RabbitMQ."""

from __future__ import annotations

import json
import logging
import os
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ...shared.broker import publish_event
from ...shared.events import EventEnvelope
from ...shared.timeutils import utcnow
from .models import OutboxEvent, OutboxStatus

logger = logging.getLogger(__name__)


def _max_attempts() -> int:
    return int(os.getenv("OUTBOX_MAX_ATTEMPTS", "10"))


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


async def relay_pending_events(session: AsyncSession, *, batch_size: int = 50) -> int:
    """Publish pending outbox rows to the broker and mark them published."""
    rows = (
        (
            await session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.status == OutboxStatus.PENDING)
                .order_by(OutboxEvent.created_at)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )

    published = 0
    for row in rows:
        try:
            envelope = json.loads(row.payload)
            await publish_event(row.event_type, envelope)
            row.status = OutboxStatus.PUBLISHED
            row.published_at = utcnow()
            row.last_error = None
            published += 1
        except Exception as exc:  # noqa: BLE001
            row.attempts = int(row.attempts or 0) + 1
            row.last_error = str(exc)[:1000]
            if row.attempts >= _max_attempts():
                row.status = OutboxStatus.FAILED
                logger.error(
                    "Outbox event_id=%s type=%s failed permanently after %s attempts: %s",
                    row.event_id,
                    row.event_type,
                    row.attempts,
                    exc,
                )
            else:
                logger.warning(
                    "Outbox publish failed event_id=%s type=%s attempt=%s: %s",
                    row.event_id,
                    row.event_type,
                    row.attempts,
                    exc,
                )

    await session.commit()
    return published


async def flush_outbox() -> int:
    """Open a short-lived session and relay pending events (post-commit kick)."""
    from .db import SessionLocal

    async with SessionLocal() as session:
        return await relay_pending_events(session)
