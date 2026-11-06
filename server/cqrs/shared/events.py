"""Integration event contracts shared by command and query services.

These are transport DTOs only — never import write or read persistence models here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .timeutils import utcnow


class EventEnvelope(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    occurred_at: datetime = Field(default_factory=utcnow)
    actor_id: str | None = None
    payload: Any


class MatchParsedEvent(EventEnvelope):
    event_type: str = "MatchParsed"


class LogEventCreatedEvent(EventEnvelope):
    event_type: str = "LogEventCreated"


class RatingsRebuildRequestedEvent(EventEnvelope):
    event_type: str = "RatingsRebuildRequested"


class RatingsRebuiltEvent(EventEnvelope):
    event_type: str = "RatingsRebuilt"


class PlayerAliasUpdatedEvent(EventEnvelope):
    event_type: str = "PlayerAliasUpdated"


class TournamentCreatedEvent(EventEnvelope):
    event_type: str = "TournamentCreated"


class TournamentUpdatedEvent(EventEnvelope):
    event_type: str = "TournamentUpdated"


class EventCreatedEvent(EventEnvelope):
    event_type: str = "EventCreated"


class EventUpdatedEvent(EventEnvelope):
    event_type: str = "EventUpdated"


class TournamentLinkedToEventEvent(EventEnvelope):
    event_type: str = "TournamentLinkedToEvent"


class MatchTournamentAssignedEvent(EventEnvelope):
    event_type: str = "MatchTournamentAssigned"
