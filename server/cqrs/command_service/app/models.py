"""Write-side persistence models (command store)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlmodel import Field

from ...shared.auth.roles import UserRole
from ...shared.timeutils import utcnow
from .db import CommandSQLModel


class OutboxStatus(str, Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"


class RawLogEvent(CommandSQLModel, table=True):
    __tablename__ = "raw_log_events"

    id: int | None = Field(default=None, primary_key=True)
    source_log_id: int | None = Field(default=None, index=True, unique=True)
    content_hash: str | None = Field(default=None, index=True, unique=True)
    match_id: str = Field(index=True, unique=True)
    raw_log: str
    map_name: str
    blu_score: int
    red_score: int
    timestamp: datetime = Field(default_factory=utcnow)
    actor_id: str | None = Field(default=None, index=True)
    tournament_id: str | None = Field(default=None, index=True)


class OutboxEvent(CommandSQLModel, table=True):
    """Transactional outbox row — staged with domain writes, relayed to RabbitMQ."""

    __tablename__ = "outbox_events"

    id: int | None = Field(default=None, primary_key=True)
    event_id: UUID = Field(index=True, unique=True)
    event_type: str = Field(index=True)
    payload: str
    status: OutboxStatus = Field(default=OutboxStatus.PENDING, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    published_at: datetime | None = Field(default=None)
    attempts: int = Field(default=0)
    last_error: str | None = Field(default=None)


class User(CommandSQLModel, table=True):
    """Authenticated account bound to a Steam identity (write-side aggregate)."""

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    steam_id: str = Field(index=True, unique=True)
    display_name: str = Field(default="")
    avatar_url: str | None = Field(default=None)
    role: UserRole = Field(default=UserRole.PLAYER, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    last_login_at: datetime | None = Field(default=None)


class AuthLoginCode(CommandSQLModel, table=True):
    """One-time Steam login code exchanged for a JWT (avoids token-in-URL redirects)."""

    __tablename__ = "auth_login_codes"

    code: str = Field(primary_key=True)
    token: str
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    used_at: datetime | None = Field(default=None)


class EventRecord(CommandSQLModel, table=True):
    """Admin-managed event aggregate on the write side."""

    __tablename__ = "events"

    event_id: str = Field(primary_key=True)
    name: str
    slug: str = Field(index=True, unique=True)
    start_date: datetime | None = Field(default=None)
    end_date: datetime | None = Field(default=None)
    created_by: str = Field(index=True)
    updated_by: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class TournamentRecord(CommandSQLModel, table=True):
    """Admin-managed tournament aggregate on the write side."""

    __tablename__ = "tournaments"

    tournament_id: str = Field(primary_key=True)
    event_id: str | None = Field(
        default=None, foreign_key="events.event_id", index=True
    )
    name: str
    slug: str = Field(index=True, unique=True)
    start_date: datetime | None = Field(default=None)
    end_date: datetime | None = Field(default=None)
    created_by: str = Field(index=True)
    updated_by: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
