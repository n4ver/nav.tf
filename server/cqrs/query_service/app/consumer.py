"""Event consumer that projects integration events into the read database."""

from __future__ import annotations

import logging
from typing import Any

from ...shared.broker import BROKER, EventHandler
from .db import SessionLocal
from .services import ProjectionService

logger = logging.getLogger(__name__)


async def handle_integration_event(event_type: str, payload: dict[str, Any]) -> None:
    async with SessionLocal() as session:
        service = ProjectionService(session)
        try:
            await service.handle_event(event_type, payload)
        except Exception:
            logger.exception("Failed projecting event_type=%s", event_type)
            await session.rollback()
            raise


def start_event_consumer(handler: EventHandler | None = None) -> None:
    BROKER.subscribe(handler or handle_integration_event)
