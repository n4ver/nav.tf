"""Idempotent RabbitMQ consumer for the query service read model."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from .db import SessionLocal
from .models import ProcessedEvent
from .services import ProjectionService

logger = logging.getLogger(__name__)


def _extract_event_id(envelope: dict[str, Any]) -> UUID | None:
    raw = envelope.get("event_id")
    if raw is None:
        return None
    try:
        return raw if isinstance(raw, UUID) else UUID(str(raw))
    except (TypeError, ValueError):
        return None


async def handle_integration_event_idempotent(
    event_type: str,
    envelope: dict[str, Any],
) -> None:
    """Apply an integration event at most once per event_id."""
    event_id = _extract_event_id(envelope)

    async with SessionLocal() as session:
        if event_id is not None:
            existing = await session.get(ProcessedEvent, event_id)
            if existing is not None:
                logger.info(
                    "Skipping duplicate event_id=%s type=%s",
                    event_id,
                    event_type,
                )
                return

        service = ProjectionService(session)
        try:
            await service.handle_event(event_type, envelope)
            if event_id is not None:
                session.add(ProcessedEvent(event_id=event_id, event_type=event_type))
            await session.commit()
        except IntegrityError:
            # Concurrent worker claimed the same event_id.
            await session.rollback()
            logger.info(
                "Concurrent duplicate event_id=%s type=%s",
                event_id,
                event_type,
            )
        except Exception:
            await session.rollback()
            logger.exception("Failed projecting event_type=%s", event_type)
            raise
