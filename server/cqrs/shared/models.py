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
    PlayerStatsView,
    PlayerStatSnapshot,
    RawLogUpload,
    TournamentCommandModel,
    TournamentSummaryView,
)

__all__ = [
    "CachedLogIngest",
    "EventEnvelope",
    "LogEventCreatedEvent",
    "MatchParsedEvent",
    "RatingsRebuildRequestedEvent",
    "RatingsRebuiltEvent",
    "MatchCommandModel",
    "MatchSummaryView",
    "PlayerLifetimeStatsView",
    "PlayerStatsView",
    "PlayerStatSnapshot",
    "RawLogUpload",
    "TournamentCommandModel",
    "TournamentSummaryView",
]
