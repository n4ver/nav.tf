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


# --- Ordering, backoff and parking (drive the relay directly, no app workers) ---

from datetime import timedelta

from cqrs.command_service.app import outbox_admin
from cqrs.command_service.app.outbox import (
    outbox_status_counts,
    requeue_failed_events,
)
from cqrs.shared.timeutils import utcnow


async def _stage(*match_ids: str) -> list:
    envelopes = [
        MatchParsedEvent(payload={"match_id": mid, "players": []}) for mid in match_ids
    ]
    async with SessionLocal() as session:
        for envelope in envelopes:
            await stage_event(session, envelope)
        await session.commit()
    return envelopes


async def _row(event_id) -> OutboxEvent:
    async with SessionLocal() as session:
        return (
            (
                await session.execute(
                    select(OutboxEvent).where(OutboxEvent.event_id == event_id)
                )
            )
            .scalars()
            .one()
        )


@pytest.mark.asyncio
async def test_failed_head_blocks_later_events_and_backs_off(clean_dbs, monkeypatch):
    seen: list[str] = []

    async def _fail_first(event_type: str, payload):
        if payload["payload"]["match_id"] == "m-first":
            raise RuntimeError("broker down")
        seen.append(payload["payload"]["match_id"])

    monkeypatch.setattr("cqrs.command_service.app.outbox.publish_event", _fail_first)
    monkeypatch.setenv("OUTBOX_RETRY_BASE_MS", "60000")
    first, second = await _stage("m-first", "m-second")

    assert await flush_outbox() == 0
    # The second event must not overtake the failed first one.
    assert seen == []
    head = await _row(first.event_id)
    assert head.status == OutboxStatus.PENDING
    assert head.attempts == 1
    assert head.next_attempt_at is not None
    assert head.next_attempt_at - utcnow() > timedelta(seconds=50)
    assert (await _row(second.event_id)).attempts == 0

    # While the head is backing off, a kick publishes nothing and leaves it alone.
    assert await flush_outbox() == 0
    assert (await _row(first.event_id)).attempts == 1


@pytest.mark.asyncio
async def test_relay_publishes_in_order_once_head_recovers(clean_dbs, monkeypatch):
    seen: list[str] = []
    state = {"down": True}

    async def _publish(event_type: str, payload):
        if state["down"]:
            raise RuntimeError("broker down")
        seen.append(payload["payload"]["match_id"])

    monkeypatch.setattr("cqrs.command_service.app.outbox.publish_event", _publish)
    monkeypatch.setenv("OUTBOX_RETRY_BASE_MS", "0")
    await _stage("m-1", "m-2", "m-3")

    assert await flush_outbox() == 0
    state["down"] = False
    assert await flush_outbox() == 3
    assert seen == ["m-1", "m-2", "m-3"]


@pytest.mark.asyncio
async def test_exhausted_row_is_parked_and_stops_blocking(clean_dbs, monkeypatch):
    seen: list[str] = []

    async def _publish(event_type: str, payload):
        if payload["payload"]["match_id"] == "m-poison":
            raise RuntimeError("rejected")
        seen.append(payload["payload"]["match_id"])

    monkeypatch.setattr("cqrs.command_service.app.outbox.publish_event", _publish)
    monkeypatch.setenv("OUTBOX_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("OUTBOX_RETRY_BASE_MS", "0")
    poison, _after = await _stage("m-poison", "m-after")

    assert await flush_outbox() == 0  # attempt 1: backs off, blocks
    assert seen == []
    assert await flush_outbox() == 1  # attempt 2: parked, next row proceeds
    assert seen == ["m-after"]

    parked = await _row(poison.event_id)
    assert parked.status == OutboxStatus.FAILED
    assert parked.attempts == 2
    assert parked.last_error == "rejected"


@pytest.mark.asyncio
async def test_unreadable_payload_is_parked_without_publishing(clean_dbs, monkeypatch):
    seen: list[str] = []

    async def _publish(event_type: str, payload):
        seen.append(payload["payload"]["match_id"])

    monkeypatch.setattr("cqrs.command_service.app.outbox.publish_event", _publish)
    corrupt, _ok = await _stage("m-corrupt", "m-ok")
    async with SessionLocal() as session:
        row = (
            (
                await session.execute(
                    select(OutboxEvent).where(OutboxEvent.event_id == corrupt.event_id)
                )
            )
            .scalars()
            .one()
        )
        row.payload = "{not json"
        await session.commit()

    assert await flush_outbox() == 1
    assert seen == ["m-ok"]
    parked = await _row(corrupt.event_id)
    assert parked.status == OutboxStatus.FAILED
    assert "unreadable payload" in (parked.last_error or "")


@pytest.mark.asyncio
async def test_worker_relay_skips_when_lock_is_held(clean_dbs, monkeypatch):
    from sqlalchemy import text

    from cqrs.command_service.app.outbox import RELAY_LOCK_KEY

    calls = {"n": 0}

    async def _publish(event_type: str, payload):
        calls["n"] += 1

    monkeypatch.setattr("cqrs.command_service.app.outbox.publish_event", _publish)
    await _stage("m-locked")

    async with SessionLocal() as holder:
        await holder.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": RELAY_LOCK_KEY}
        )
        assert await flush_outbox(wait_for_lock=False) == 0
        await holder.rollback()

    assert calls["n"] == 0
    assert await flush_outbox(wait_for_lock=False) == 1


@pytest.mark.asyncio
async def test_requeue_failed_events_resets_retry_budget(clean_dbs, monkeypatch):
    async def _fail(event_type: str, payload):
        raise RuntimeError("down")

    monkeypatch.setattr("cqrs.command_service.app.outbox.publish_event", _fail)
    monkeypatch.setenv("OUTBOX_MAX_ATTEMPTS", "1")
    first, second = await _stage("m-a", "m-b")
    await flush_outbox()
    await flush_outbox()

    async with SessionLocal() as session:
        counts = await outbox_status_counts(session)
    assert counts["failed"] == 2
    assert counts["pending"] == 0

    async with SessionLocal() as session:
        assert await requeue_failed_events(session, [first.event_id]) == 1
    row = await _row(first.event_id)
    assert row.status == OutboxStatus.PENDING
    assert row.attempts == 0
    assert row.next_attempt_at is None
    assert row.last_error is None
    assert (await _row(second.event_id)).status == OutboxStatus.FAILED

    async with SessionLocal() as session:
        assert await requeue_failed_events(session) == 1


def test_outbox_admin_cli_status_and_requeue(clean_dbs, capsys):
    assert outbox_admin.main(["status"]) == 0
    assert '"pending": 0' in capsys.readouterr().out
    assert outbox_admin.main(["requeue-failed"]) == 0
    assert "Requeued 0 outbox event(s)." in capsys.readouterr().out
