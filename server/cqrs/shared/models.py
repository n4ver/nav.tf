"""Backward-compatible re-exports. Prefer shared.schemas / shared.events."""

from .events import (
    EventEnvelope,
    LogEventCreatedEvent,
    MatchParsedEvent,
    RatingsRebuildRequestedEvent,
    RatingsRebuiltEvent,
)
from .schemas import (
    CachedLogIngest,
    MatchCommandModel,
    MatchSummaryView,
    PlayerLifetimeStatsView,
    PlayerStatSnapshot,
    PlayerStatsView,
    RawLogUpload,
    TournamentCommandModel,
    TournamentSummaryView,
)

__all__ = [
    "CachedLogIngest",
    "EventEnvelope",
    "LogEventCreatedEvent",
    "MatchCommandModel",
    "MatchParsedEvent",
    "MatchSummaryView",
    "PlayerLifetimeStatsView",
    "PlayerStatSnapshot",
    "PlayerStatsView",
    "RatingsRebuildRequestedEvent",
    "RatingsRebuiltEvent",
    "RawLogUpload",
    "TournamentCommandModel",
    "TournamentSummaryView",
]
