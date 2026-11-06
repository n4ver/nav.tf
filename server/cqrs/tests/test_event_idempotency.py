"""Event idempotency tests for the query-side consumer."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from cqrs.query_service.app.db import SessionLocal
from cqrs.query_service.app.idempotency import handle_integration_event_idempotent
from cqrs.query_service.app.models import MatchSummaryProjection, ProcessedEvent
from cqrs.query_service.app.services import (
    ProjectionDependencyMissing,
    ProjectionService,
)
from cqrs.shared.events import MatchParsedEvent


def _match_envelope(match_id: str, *, event_id=None) -> dict:
    event = MatchParsedEvent(
        event_id=event_id or uuid4(),
        payload={
            "match_id": match_id,
            "map_name": "cp_process_final",
            "blu_score": 5,
            "red_score": 2,
            "duration_seconds": 1800,
            "date_played": "2024-01-01T12:00:00",
            "tournament": {
                "tournament_id": "default-tournament",
                "name": "Default",
                "slug": "default-tournament",
            },
            "players": [
                {
                    "steam_id": "[U:1:100]",
                    "team": "Blue",
                    "classes_played": ["scout"],
                    "primary_class": "scout",
                    "kills": 10,
                    "deaths": 5,
                    "assists": 3,
                    "damage_per_minute": 300,
                    "playtime_seconds": 1800,
                }
            ],
        },
    )
    return event.model_dump(mode="json")


@pytest.mark.asyncio
async def test_duplicate_event_id_is_skipped(client):
    match_id = str(uuid4())
    envelope = _match_envelope(match_id)
    event_id = envelope["event_id"]

    await handle_integration_event_idempotent("MatchParsed", envelope)
    await handle_integration_event_idempotent("MatchParsed", envelope)

    async with SessionLocal() as session:
        processed = await session.get(ProcessedEvent, event_id)
        assert processed is not None
        assert processed.event_type == "MatchParsed"

        matches = (
            (
                await session.execute(
                    select(MatchSummaryProjection).where(
                        MatchSummaryProjection.match_id == match_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(matches) == 1
        assert matches[0].ratings_ready is True


@pytest.mark.asyncio
async def test_different_event_id_same_match_upserts(client):
    match_id = str(uuid4())
    first = _match_envelope(match_id)
    second = _match_envelope(match_id)
    second["payload"]["blu_score"] = 8

    await handle_integration_event_idempotent("MatchParsed", first)
    await handle_integration_event_idempotent("MatchParsed", second)

    async with SessionLocal() as session:
        row = await session.get(MatchSummaryProjection, match_id)
        assert row is not None
        assert row.blu_score == 8
        count = (await session.execute(select(ProcessedEvent))).scalars().all()
        assert len(count) == 2


@pytest.mark.asyncio
async def test_projection_integrity_error_is_not_mistaken_for_duplicate(
    clean_dbs, monkeypatch
):
    async def violates_constraint(self, event_type, envelope):
        raise IntegrityError("INSERT ...", {}, Exception("unique violation"))

    monkeypatch.setattr(ProjectionService, "handle_event", violates_constraint)
    envelope = _match_envelope(str(uuid4()))

    with pytest.raises(IntegrityError):
        await handle_integration_event_idempotent("MatchParsed", envelope)

    # The claim was rolled back with the projection, so a retry can apply it.
    async with SessionLocal() as session:
        assert await session.get(ProcessedEvent, envelope["event_id"]) is None


@pytest.mark.asyncio
async def test_assignment_for_unprojected_match_fails_instead_of_acking(clean_dbs):
    envelope = {
        "event_id": str(uuid4()),
        "event_type": "MatchTournamentAssigned",
        "payload": {"match_id": "never-projected", "tournament_id": "t-1"},
    }
    with pytest.raises(ProjectionDependencyMissing):
        await handle_integration_event_idempotent("MatchTournamentAssigned", envelope)

    async with SessionLocal() as session:
        assert await session.get(ProcessedEvent, envelope["event_id"]) is None
