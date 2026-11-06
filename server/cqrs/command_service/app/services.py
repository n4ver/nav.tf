"""Command handlers: persist write models and publish integration events."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ...shared.event_ids import stable_event_uuid_from_slug
from ...shared.events import (
    EventCreatedEvent,
    EventUpdatedEvent,
    LogEventCreatedEvent,
    MatchParsedEvent,
    MatchTournamentAssignedEvent,
    PlayerAliasUpdatedEvent,
    TournamentCreatedEvent,
    TournamentLinkedToEventEvent,
    TournamentUpdatedEvent,
)
from ...shared.schemas import (
    AssignMatchTournamentCommand,
    CachedLogIngest,
    CreateEventCommand,
    CreateTournamentCommand,
    IngestLogsTfCommand,
    LinkTournamentToEventCommand,
    RawLogUpload,
    TournamentCommandModel,
    UpdateEventCommand,
    UpdatePlayerDisplayNameCommand,
    UpdateTournamentCommand,
)
from ...shared.seed_cache import get_cached_log_data
from ...shared.steam import canonical_steam_id
from ...shared.timeutils import ensure_utc_naive, utcnow
from ...shared.tournaments import (
    build_tournament_command,
    build_tournament_command_from_slug,
    builtin_tournament_command,
    stable_tournament_uuid_from_slug,
)
from .logs_tf_parser import parse_logs_tf
from .models import EventRecord, RawLogEvent, TournamentRecord
from .outbox import flush_outbox, stage_event
from .parsers import parse_srcds_log

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LOGS_TF_API_BASE = "https://logs.tf/api/v1/log"


def _content_hash(raw_log: str) -> str:
    normalized = "\n".join(line.rstrip() for line in raw_log.strip().splitlines())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _json_content_hash(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_slug(slug: str) -> str:
    normalized = (slug or "").strip().lower().replace(" ", "-")
    if not _SLUG_RE.match(normalized):
        raise HTTPException(
            status_code=400,
            detail="Slug must be lowercase alphanumeric with optional hyphens",
        )
    return normalized


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _timestamp_from_logs_tf(data: dict[str, Any]) -> datetime:
    info = data.get("info") or {}
    raw_date = info.get("date")
    if raw_date is None:
        return utcnow()
    try:
        return datetime.fromtimestamp(int(raw_date), tz=UTC).replace(tzinfo=None)
    except (TypeError, ValueError, OSError, OverflowError):
        return utcnow()


class CommandService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _require_event(self, event_id: str) -> EventRecord:
        record = await self.session.get(EventRecord, event_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Event not found")
        return record

    async def _resolve_optional_event_id(self, event_id: Any) -> str | None:
        if event_id is None:
            return None
        resolved = str(event_id)
        await self._require_event(resolved)
        return resolved

    async def _get_tournament(
        self, tournament_id: str, *, actor_id: str
    ) -> TournamentRecord | None:
        """Load a write-side tournament, materializing a built-in one on first use.

        Catalog brackets and the default tournament reach the read model through
        ingest without a write-side record; create it so admins can manage them.
        """
        record = await self.session.get(TournamentRecord, tournament_id)
        if record is not None:
            return record
        builtin = builtin_tournament_command(tournament_id)
        if builtin is None:
            return None
        slug_taken = (
            (
                await self.session.execute(
                    select(TournamentRecord).where(TournamentRecord.slug == builtin.slug)
                )
            )
            .scalars()
            .first()
        )
        if slug_taken is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Tournament slug already exists: {builtin.slug}",
            )
        now = utcnow()
        record = TournamentRecord(
            tournament_id=tournament_id,
            name=builtin.name,
            slug=builtin.slug,
            created_by=actor_id,
            updated_by=actor_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def _resolve_ingest_tournament(
        self,
        tournament_id: Any,
        *,
        start_date,
    ) -> TournamentCommandModel:
        if tournament_id is None:
            return build_tournament_command_from_slug(
                "default-tournament",
                start_date=start_date,
            )
        record = await self.session.get(TournamentRecord, str(tournament_id))
        if record is None:
            builtin = builtin_tournament_command(str(tournament_id))
            if builtin is None:
                raise HTTPException(status_code=404, detail="Tournament not found")
            return builtin.model_copy(update={"start_date": start_date})
        return TournamentCommandModel(
            tournament_id=record.tournament_id,  # type: ignore[arg-type]
            name=record.name,
            slug=record.slug,
            start_date=record.start_date,
            end_date=record.end_date,
            event_id=record.event_id,  # type: ignore[arg-type]
        )

    def _tournament_mutation_payload(self, record: TournamentRecord) -> dict[str, object]:
        return {
            "tournament_id": record.tournament_id,
            "name": record.name,
            "slug": record.slug,
            "start_date": _iso_or_none(record.start_date),
            "end_date": _iso_or_none(record.end_date),
            "event_id": record.event_id,
        }

    async def upload_log(
        self,
        payload: RawLogUpload,
        *,
        actor_id: str,
    ) -> dict[str, object]:
        if not payload.log_data.strip():
            raise HTTPException(status_code=400, detail="Log data cannot be empty")

        content_hash = _content_hash(payload.log_data)
        existing = (
            (
                await self.session.execute(
                    select(RawLogEvent).where(RawLogEvent.content_hash == content_hash)
                )
            )
            .scalars()
            .first()
        )
        if existing:
            return {
                "match_id": existing.match_id,
                "log_id": existing.source_log_id,
                "status": "skipped",
            }

        parsed_match = parse_srcds_log(payload.log_data)
        # Stable match id for identical payloads so projections stay idempotent.
        parsed_match.match_id = uuid5(NAMESPACE_URL, f"upload:{content_hash}")
        tournament = await self._resolve_ingest_tournament(
            payload.tournament_id, start_date=payload.timestamp
        )
        return await self._persist_and_publish(
            parsed_match=parsed_match,
            raw_log=payload.log_data,
            timestamp=payload.timestamp,
            tournament=tournament,
            source_log_id=None,
            content_hash=content_hash,
            actor_id=actor_id,
        )

    async def ingest_cached_log(
        self,
        payload: CachedLogIngest,
        *,
        actor_id: str,
    ) -> dict[str, object]:
        existing = (
            (
                await self.session.execute(
                    select(RawLogEvent).where(
                        RawLogEvent.source_log_id == payload.log_id
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing:
            return {
                "log_id": payload.log_id,
                "match_id": existing.match_id,
                "status": "skipped",
            }

        log_data = payload.data
        if log_data is None:
            try:
                log_data = get_cached_log_data(payload.log_id)
            except FileNotFoundError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

        content_hash = _json_content_hash(log_data)
        existing_hash = (
            (
                await self.session.execute(
                    select(RawLogEvent).where(RawLogEvent.content_hash == content_hash)
                )
            )
            .scalars()
            .first()
        )
        if existing_hash:
            return {
                "log_id": existing_hash.source_log_id,
                "match_id": existing_hash.match_id,
                "status": "skipped",
            }

        parsed_match = parse_logs_tf(log_data, payload.log_id)
        tournament = build_tournament_command(payload.tournament_id, payload.timestamp)
        record = await self.session.get(TournamentRecord, str(tournament.tournament_id))
        if record is not None:
            # Carry the admin-managed name and event link; the bare catalog entry has
            # event_id=None, which the read model would apply as an unlink.
            tournament = TournamentCommandModel(
                tournament_id=record.tournament_id,  # type: ignore[arg-type]
                name=record.name,
                slug=record.slug,
                start_date=payload.timestamp,
                event_id=record.event_id,  # type: ignore[arg-type]
            )
        return await self._persist_and_publish(
            parsed_match=parsed_match,
            raw_log=f"logs.tf:{payload.log_id}",
            timestamp=payload.timestamp,
            tournament=tournament,
            source_log_id=payload.log_id,
            content_hash=content_hash,
            actor_id=actor_id,
        )

    async def ingest_logs_tf(
        self,
        payload: IngestLogsTfCommand,
        *,
        actor_id: str,
    ) -> dict[str, object]:
        """Fetch a log from logs.tf, parse it, persist, and publish MatchParsed."""
        logstf_id = payload.logstf_id

        existing = (
            (
                await self.session.execute(
                    select(RawLogEvent).where(RawLogEvent.source_log_id == logstf_id)
                )
            )
            .scalars()
            .first()
        )
        if existing:
            return {
                "log_id": logstf_id,
                "match_id": existing.match_id,
                "status": "skipped",
            }

        log_data = await self._fetch_logs_tf_json(logstf_id)

        content_hash = _json_content_hash(log_data)
        existing_hash = (
            (
                await self.session.execute(
                    select(RawLogEvent).where(RawLogEvent.content_hash == content_hash)
                )
            )
            .scalars()
            .first()
        )
        if existing_hash:
            return {
                "log_id": existing_hash.source_log_id,
                "match_id": existing_hash.match_id,
                "status": "skipped",
            }

        timestamp = _timestamp_from_logs_tf(log_data)
        parsed_match = parse_logs_tf(log_data, logstf_id)
        tournament = await self._resolve_ingest_tournament(
            payload.tournament_id, start_date=timestamp
        )
        return await self._persist_and_publish(
            parsed_match=parsed_match,
            raw_log=f"logs.tf:{logstf_id}",
            timestamp=timestamp,
            tournament=tournament,
            source_log_id=logstf_id,
            content_hash=content_hash,
            actor_id=actor_id,
        )

    async def _fetch_logs_tf_json(self, logstf_id: int) -> dict[str, Any]:
        url = f"{LOGS_TF_API_BASE}/{logstf_id}"
        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                response = await client.get(url)
        except httpx.HTTPError as exc:
            logger.exception("logs.tf fetch failed for %s", logstf_id)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to reach logs.tf: {exc}",
            ) from exc

        if response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"logs.tf log not found: {logstf_id}",
            )
        if response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"logs.tf returned HTTP {response.status_code}",
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=502,
                detail="logs.tf returned invalid JSON",
            ) from exc

        if not isinstance(data, dict):
            raise HTTPException(
                status_code=502, detail="logs.tf returned unexpected payload"
            )
        if data.get("success") is False:
            raise HTTPException(
                status_code=404,
                detail=f"logs.tf log not found: {logstf_id}",
            )
        return data

    async def update_player_display_name(
        self,
        command: UpdatePlayerDisplayNameCommand,
        *,
        actor_id: str,
    ) -> dict[str, object]:
        steam_id = canonical_steam_id(command.steam_id.strip())
        display_name = command.display_name.strip()
        if not steam_id:
            raise HTTPException(status_code=400, detail="steam_id is required")
        if not display_name:
            raise HTTPException(status_code=400, detail="display_name is required")

        event = PlayerAliasUpdatedEvent(
            actor_id=actor_id,
            payload={
                "steam_id": steam_id,
                "display_name": display_name,
            },
        )
        await stage_event(self.session, event)
        await self.session.commit()
        await flush_outbox()
        return {
            "steam_id": steam_id,
            "display_name": display_name,
            "status": "accepted",
        }

    async def create_tournament(
        self,
        command: CreateTournamentCommand,
        *,
        actor_id: str,
    ) -> dict[str, object]:
        slug = _normalize_slug(command.slug)
        name = command.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name is required")

        existing = (
            (
                await self.session.execute(
                    select(TournamentRecord).where(TournamentRecord.slug == slug)
                )
            )
            .scalars()
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=409, detail=f"Tournament slug already exists: {slug}"
            )

        tournament_id = str(stable_tournament_uuid_from_slug(slug))
        now = utcnow()
        linked_event_id = await self._resolve_optional_event_id(command.event_id)
        record = TournamentRecord(
            tournament_id=tournament_id,
            event_id=linked_event_id,
            name=name,
            slug=slug,
            start_date=ensure_utc_naive(command.start_date)
            if command.start_date
            else None,
            end_date=ensure_utc_naive(command.end_date) if command.end_date else None,
            created_by=actor_id,
            updated_by=actor_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(record)
        payload = self._tournament_mutation_payload(record)
        event = TournamentCreatedEvent(actor_id=actor_id, payload=payload)
        await stage_event(self.session, event)
        if linked_event_id:
            await stage_event(
                self.session,
                TournamentLinkedToEventEvent(
                    actor_id=actor_id,
                    payload={
                        "tournament_id": tournament_id,
                        "event_id": linked_event_id,
                    },
                ),
            )
        await self.session.commit()
        await flush_outbox()
        return {**payload, "status": "accepted"}

    async def update_tournament(
        self,
        tournament_id: str,
        command: UpdateTournamentCommand,
        *,
        actor_id: str,
    ) -> dict[str, object]:
        record = await self.session.get(TournamentRecord, tournament_id)
        now = utcnow()
        previous_event_id: str | None = None
        if record is None:
            # Promote a query-projected / catalog tournament into the write model.
            name = (command.name or "").strip()
            slug = _normalize_slug(command.slug) if command.slug else ""
            if not name or not slug:
                raise HTTPException(
                    status_code=404,
                    detail="Tournament not found on write side; provide name and slug to claim it",
                )
            conflict = (
                (
                    await self.session.execute(
                        select(TournamentRecord).where(TournamentRecord.slug == slug)
                    )
                )
                .scalars()
                .first()
            )
            if conflict:
                raise HTTPException(
                    status_code=409, detail=f"Tournament slug already exists: {slug}"
                )
            linked_event_id = (
                await self._resolve_optional_event_id(command.event_id)
                if command.event_id is not None
                else None
            )
            record = TournamentRecord(
                tournament_id=tournament_id,
                event_id=linked_event_id,
                name=name,
                slug=slug,
                start_date=ensure_utc_naive(command.start_date)
                if command.start_date
                else None,
                end_date=ensure_utc_naive(command.end_date)
                if command.end_date
                else None,
                created_by=actor_id,
                updated_by=actor_id,
                created_at=now,
                updated_at=now,
            )
            self.session.add(record)
            payload = self._tournament_mutation_payload(record)
            event = TournamentUpdatedEvent(actor_id=actor_id, payload=payload)
            await stage_event(self.session, event)
            if linked_event_id:
                await stage_event(
                    self.session,
                    TournamentLinkedToEventEvent(
                        actor_id=actor_id,
                        payload={
                            "tournament_id": record.tournament_id,
                            "event_id": linked_event_id,
                        },
                    ),
                )
            await self.session.commit()
            await flush_outbox()
            return {**payload, "status": "accepted"}

        previous_event_id = record.event_id
        if command.name is not None:
            name = command.name.strip()
            if not name:
                raise HTTPException(status_code=400, detail="name cannot be empty")
            record.name = name
        if command.slug is not None:
            slug = _normalize_slug(command.slug)
            conflict = (
                (
                    await self.session.execute(
                        select(TournamentRecord).where(
                            TournamentRecord.slug == slug,
                            TournamentRecord.tournament_id != tournament_id,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if conflict:
                raise HTTPException(
                    status_code=409, detail=f"Tournament slug already exists: {slug}"
                )
            record.slug = slug
        if command.start_date is not None:
            record.start_date = ensure_utc_naive(command.start_date)
        if command.end_date is not None:
            record.end_date = ensure_utc_naive(command.end_date)
        event_link_changed = False
        if "event_id" in command.model_fields_set:
            record.event_id = await self._resolve_optional_event_id(command.event_id)
            event_link_changed = record.event_id != previous_event_id

        record.updated_by = actor_id
        record.updated_at = now

        payload = self._tournament_mutation_payload(record)
        event = TournamentUpdatedEvent(actor_id=actor_id, payload=payload)
        await stage_event(self.session, event)
        if event_link_changed:
            await stage_event(
                self.session,
                TournamentLinkedToEventEvent(
                    actor_id=actor_id,
                    payload={
                        "tournament_id": record.tournament_id,
                        "event_id": record.event_id,
                    },
                ),
            )
        await self.session.commit()
        await flush_outbox()
        return {**payload, "status": "accepted"}

    async def create_event(
        self,
        command: CreateEventCommand,
        *,
        actor_id: str,
    ) -> dict[str, object]:
        slug = _normalize_slug(command.slug)
        name = command.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name is required")

        existing = (
            (
                await self.session.execute(
                    select(EventRecord).where(EventRecord.slug == slug)
                )
            )
            .scalars()
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=409, detail=f"Event slug already exists: {slug}"
            )

        event_id = str(stable_event_uuid_from_slug(slug))
        now = utcnow()
        record = EventRecord(
            event_id=event_id,
            name=name,
            slug=slug,
            start_date=ensure_utc_naive(command.start_date)
            if command.start_date
            else None,
            end_date=ensure_utc_naive(command.end_date) if command.end_date else None,
            created_by=actor_id,
            updated_by=actor_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(record)
        payload = {
            "event_id": event_id,
            "name": name,
            "slug": slug,
            "start_date": record.start_date.isoformat() if record.start_date else None,
            "end_date": record.end_date.isoformat() if record.end_date else None,
        }
        event = EventCreatedEvent(actor_id=actor_id, payload=payload)
        await stage_event(self.session, event)
        await self.session.commit()
        await flush_outbox()
        return {**payload, "status": "accepted"}

    async def update_event(
        self,
        event_id: str,
        command: UpdateEventCommand,
        *,
        actor_id: str,
    ) -> dict[str, object]:
        record = await self.session.get(EventRecord, event_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Event not found")

        now = utcnow()
        if command.name is not None:
            name = command.name.strip()
            if not name:
                raise HTTPException(status_code=400, detail="name cannot be empty")
            record.name = name
        if command.slug is not None:
            slug = _normalize_slug(command.slug)
            conflict = (
                (
                    await self.session.execute(
                        select(EventRecord).where(
                            EventRecord.slug == slug,
                            EventRecord.event_id != event_id,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if conflict:
                raise HTTPException(
                    status_code=409, detail=f"Event slug already exists: {slug}"
                )
            record.slug = slug
        if command.start_date is not None:
            record.start_date = ensure_utc_naive(command.start_date)
        if command.end_date is not None:
            record.end_date = ensure_utc_naive(command.end_date)

        record.updated_by = actor_id
        record.updated_at = now

        payload = {
            "event_id": record.event_id,
            "name": record.name,
            "slug": record.slug,
            "start_date": record.start_date.isoformat() if record.start_date else None,
            "end_date": record.end_date.isoformat() if record.end_date else None,
        }
        event = EventUpdatedEvent(actor_id=actor_id, payload=payload)
        await stage_event(self.session, event)
        await self.session.commit()
        await flush_outbox()
        return {**payload, "status": "accepted"}

    async def link_tournament_to_event(
        self,
        tournament_id: str,
        command: LinkTournamentToEventCommand,
        *,
        actor_id: str,
    ) -> dict[str, object]:
        tournament = await self._get_tournament(tournament_id, actor_id=actor_id)
        if tournament is None:
            raise HTTPException(status_code=404, detail="Tournament not found")

        event_id = await self._resolve_optional_event_id(command.event_id)

        now = utcnow()
        tournament.event_id = event_id
        tournament.updated_by = actor_id
        tournament.updated_at = now

        payload = {
            "tournament_id": tournament.tournament_id,
            "event_id": event_id,
        }
        event = TournamentLinkedToEventEvent(actor_id=actor_id, payload=payload)
        await stage_event(self.session, event)
        await self.session.commit()
        await flush_outbox()
        return {**payload, "status": "accepted"}

    async def assign_match_tournament(
        self,
        match_id: str,
        command: AssignMatchTournamentCommand,
        *,
        actor_id: str,
    ) -> dict[str, object]:
        tournament_id = str(command.tournament_id)
        tournament = await self._get_tournament(tournament_id, actor_id=actor_id)
        if tournament is None:
            raise HTTPException(status_code=404, detail="Tournament not found")

        raw = (
            (
                await self.session.execute(
                    select(RawLogEvent).where(RawLogEvent.match_id == str(match_id))
                )
            )
            .scalars()
            .first()
        )
        previous_tournament_id = raw.tournament_id if raw is not None else None
        if raw is not None:
            raw.tournament_id = tournament_id

        payload = {
            "match_id": str(match_id),
            "tournament_id": tournament_id,
            "previous_tournament_id": previous_tournament_id,
        }
        event = MatchTournamentAssignedEvent(actor_id=actor_id, payload=payload)
        await stage_event(self.session, event)
        await self.session.commit()
        await flush_outbox()
        return {**payload, "status": "accepted"}

    async def _persist_and_publish(
        self,
        *,
        parsed_match,
        raw_log: str,
        timestamp,
        tournament: TournamentCommandModel,
        source_log_id: int | None,
        content_hash: str | None,
        actor_id: str | None = None,
    ) -> dict[str, object]:
        match_id = str(parsed_match.match_id)

        existing_match = (
            (
                await self.session.execute(
                    select(RawLogEvent).where(RawLogEvent.match_id == match_id)
                )
            )
            .scalars()
            .first()
        )
        if existing_match:
            return {
                "match_id": existing_match.match_id,
                "log_id": existing_match.source_log_id,
                "status": "skipped",
            }

        self.session.add(
            RawLogEvent(
                source_log_id=source_log_id,
                content_hash=content_hash,
                match_id=match_id,
                raw_log=raw_log,
                map_name=parsed_match.map_name,
                blu_score=parsed_match.blu_score,
                red_score=parsed_match.red_score,
                timestamp=ensure_utc_naive(timestamp),
                actor_id=actor_id,
                tournament_id=str(tournament.tournament_id),
            )
        )

        match_payload = {
            **parsed_match.model_dump(mode="json"),
            "date_played": timestamp.isoformat(),
            "tournament": tournament.model_dump(mode="json"),
            "actor_id": actor_id,
        }
        if source_log_id is not None:
            match_payload["source_log_id"] = source_log_id

        match_event = MatchParsedEvent(actor_id=actor_id, payload=match_payload)
        created_event = LogEventCreatedEvent(
            actor_id=actor_id,
            payload={
                "match_id": match_id,
                "source_log_id": source_log_id,
                "raw_log_persisted": True,
                "actor_id": actor_id,
            },
        )

        await stage_event(self.session, match_event)
        await stage_event(self.session, created_event)
        await self.session.commit()
        await flush_outbox()

        return {
            "match_id": match_id,
            "log_id": source_log_id,
            "status": "accepted",
        }
