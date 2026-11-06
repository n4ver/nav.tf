"""Event consumer that projects integration events into the read database."""

from __future__ import annotations

from ...shared.broker import BROKER, EventHandler
from .idempotency import handle_integration_event_idempotent


def start_event_consumer(handler: EventHandler | None = None) -> None:
    BROKER.subscribe(handler or handle_integration_event_idempotent)
