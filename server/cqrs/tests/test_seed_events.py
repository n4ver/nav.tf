"""Seeding groups the Invite + Qualifier brackets into "AsiaFortress Spring 2026"."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest

from cqrs.shared.event_ids import stable_event_uuid_from_slug
from cqrs.shared.tournaments import stable_tournament_uuid

SEED_SCRIPT = Path(__file__).resolve().parents[2] / "seed" / "seed_cqrs.py"
EVENT_ID = str(stable_event_uuid_from_slug("asiafortress-spring-2026"))
INVITE_ID = str(stable_tournament_uuid(1))
QUALIFIER_ID = str(stable_tournament_uuid(2))


@pytest.fixture
def seed_module(monkeypatch):
    spec = importlib.util.spec_from_file_location("seed_cqrs_under_test", SEED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Relative URLs so requests go to the in-process command app below.
    monkeypatch.setattr(module, "COMMAND_SERVICE_URL", "")
    monkeypatch.delenv("SEED_SERVICE_TOKEN", raising=False)
    return module


class _TestClientAdapter:
    """Async `request` facade over the sync FastAPI TestClient used by the seed helpers."""

    def __init__(self, test_client) -> None:
        self._client = test_client

    async def request(self, method: str, url: str, **kwargs):
        return self._client.request(method, url, **kwargs)


def _ingest(client, log_id: int, catalog_id: int) -> None:
    response = client["command"].post(
        "/api/v1/commands/logs/ingest-cached",
        json={
            "log_id": log_id,
            "tournament_id": catalog_id,
            "section": "invite" if catalog_id == 1 else "R8",
            "data": {
                "info": {"map": f"cp_seed_{log_id}"},
                "teams": {"Blue": {"score": 1}, "Red": {"score": 0}},
                "length": 1200,
                "players": {},
            },
        },
    )
    assert response.status_code == 202, response.text


def test_seed_event_definition(seed_module):
    [(event, event_id, tournament_ids)] = seed_module._seed_event_links()

    assert event["name"] == "AsiaFortress Spring 2026"
    assert event_id == EVENT_ID
    assert tournament_ids == [INVITE_ID, QUALIFIER_ID]


def test_seed_groups_brackets_into_the_event(client, seed_module):
    adapter = _TestClientAdapter(client["command"])

    asyncio.run(seed_module._ensure_seed_events_http(adapter))
    _ingest(client, 4200001, 1)
    _ingest(client, 4200002, 2)

    event = client["query"].get(f"/api/v1/queries/events/{EVENT_ID}")
    assert event.status_code == 200, event.text
    body = event.json()
    assert body["event"]["name"] == "AsiaFortress Spring 2026"
    assert {row["tournament_id"] for row in body["tournaments"]} == {INVITE_ID, QUALIFIER_ID}

    tournaments = {
        row["tournament_id"]: row for row in client["query"].get("/api/v1/queries/tournaments").json()
    }
    assert tournaments[INVITE_ID]["event_id"] == EVENT_ID
    assert tournaments[QUALIFIER_ID]["event_id"] == EVENT_ID


def test_seed_events_are_idempotent(client, seed_module):
    adapter = _TestClientAdapter(client["command"])

    asyncio.run(seed_module._ensure_seed_events_http(adapter))
    asyncio.run(seed_module._ensure_seed_events_http(adapter))

    events = client["query"].get("/api/v1/queries/events").json()
    assert [row["event_id"] for row in events].count(EVENT_ID) == 1
