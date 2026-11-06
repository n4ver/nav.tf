"""Transactional outbox unit/integration tests."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlmodel import select

from cqrs.command_service.app.db import SessionLocal
from cqrs.command_service.app.models import OutboxEvent, OutboxStatus, RawLogEvent
from cqrs.command_service.app.outbox import flush_outbox, stage_event
from cqrs.shared.events import MatchParsedEvent


@pytest.mark.asyncio
async def test_stage_event_persists_pending_row(client):
    envelope = MatchParsedEvent(
        payload={"match_id": str(uuid4()), "players": []},
    )
    async with SessionLocal() as session:
        await stage_event(session, envelope)
        await session.commit()

        row = (
            (
                await session.execute(
                    select(OutboxEvent).where(OutboxEvent.event_id == envelope.event_id)
                )
            )
            .scalars()
            .first()
        )
        assert row is not None
        assert row.status == OutboxStatus.PENDING
        assert row.event_type == "MatchParsed"
        body = json.loads(row.payload)
        assert body["event_id"] == str(envelope.event_id)


@pytest.mark.asyncio
async def test_relay_marks_published_and_invokes_broker(client, monkeypatch):
    seen: list[tuple[str, dict]] = []

    async def _capture(event_type: str, payload):
        seen.append((event_type, payload))

    monkeypatch.setattr(
        "cqrs.command_service.app.outbox.publish_event",
        _capture,
    )

    envelope = MatchParsedEvent(payload={"match_id": "m-relay-1", "players": []})
    async with SessionLocal() as session:
        await stage_event(session, envelope)
        await session.commit()

    count = await flush_outbox()
    assert count == 1
    assert len(seen) == 1
    assert seen[0][0] == "MatchParsed"

    async with SessionLocal() as session:
        row = (
            (
                await session.execute(
                    select(OutboxEvent).where(OutboxEvent.event_id == envelope.event_id)
                )
            )
            .scalars()
            .first()
        )
        assert row is not None
        assert row.status == OutboxStatus.PUBLISHED
        assert row.published_at is not None


@pytest.mark.asyncio
async def test_relay_keeps_pending_on_broker_failure(client, monkeypatch):
    async def _fail(event_type: str, payload):
        raise RuntimeError("broker down")

    monkeypatch.setattr(
        "cqrs.command_service.app.outbox.publish_event",
        _fail,
    )
    monkeypatch.setenv("OUTBOX_MAX_ATTEMPTS", "10")

    envelope = MatchParsedEvent(payload={"match_id": "m-fail-1", "players": []})
    async with SessionLocal() as session:
        await stage_event(session, envelope)
        await session.commit()

    count = await flush_outbox()
    assert count == 0

    async with SessionLocal() as session:
        row = (
            (
                await session.execute(
                    select(OutboxEvent).where(OutboxEvent.event_id == envelope.event_id)
                )
            )
            .scalars()
            .first()
        )
        assert row is not None
        assert row.status == OutboxStatus.PENDING
        assert row.attempts >= 1
        assert row.last_error


@pytest.mark.asyncio
async def test_upload_stages_outbox_in_same_transaction(client):
    response = client["command"].post(
        "/api/v1/commands/logs/upload",
        json={
            "log_data": (
                "map_name=cp_process_final blu_score=5 red_score=2 duration=1800\n"
                "player steam_id=[U:1:100] team=Blue class=scout kills=10 deaths=5 assists=3 dpm=300\n"
            ),
            "timestamp": "2024-01-01T12:00:00Z",
        },
    )
    assert response.status_code == 202
    match_id = response.json()["match_id"]

    async with SessionLocal() as session:
        raw = (
            (
                await session.execute(
                    select(RawLogEvent).where(RawLogEvent.match_id == match_id)
                )
            )
            .scalars()
            .first()
        )
        assert raw is not None
        outbox_rows = (
            (
                await session.execute(
                    select(OutboxEvent).where(OutboxEvent.event_type == "MatchParsed")
                )
            )
            .scalars()
            .all()
        )
        assert len(outbox_rows) >= 1
        # Post-commit flush should have published already.
        assert all(row.status == OutboxStatus.PUBLISHED for row in outbox_rows)
