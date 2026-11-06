"""Event aggregate projection tests (create/link/leaderboard/reassign)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from cqrs.query_service.app.idempotency import handle_integration_event_idempotent
from cqrs.shared.events import (
    EventCreatedEvent,
    MatchParsedEvent,
    MatchTournamentAssignedEvent,
    TournamentCreatedEvent,
    TournamentLinkedToEventEvent,
)


def _event_created(event_id: str, *, name="Season One", slug="season-one") -> dict:
    return EventCreatedEvent(
        payload={
            "event_id": event_id,
            "name": name,
            "slug": slug,
            "start_date": "2026-01-01T00:00:00",
            "end_date": None,
        }
    ).model_dump(mode="json")


def _tournament_created(tournament_id: str, *, name="Invite", slug="invite") -> dict:
    return TournamentCreatedEvent(
        payload={
            "tournament_id": tournament_id,
            "name": name,
            "slug": slug,
            "start_date": None,
            "end_date": None,
            "event_id": None,
        }
    ).model_dump(mode="json")


def _match_parsed(match_id: str, tournament_id: str) -> dict:
    return MatchParsedEvent(
        payload={
            "match_id": match_id,
            "map_name": "cp_process_final",
            "blu_score": 5,
            "red_score": 2,
            "duration_seconds": 1800,
            "date_played": "2026-01-02T12:00:00",
            "tournament": {
                "tournament_id": tournament_id,
                "name": "Invite",
                "slug": "invite",
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
        }
    ).model_dump(mode="json")


@pytest.mark.asyncio
async def test_event_created_projects_list(client):
    event_id = str(uuid4())
    await handle_integration_event_idempotent("EventCreated", _event_created(event_id))

    response = client["query"].get("/api/v1/queries/events")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["event_id"] == event_id
    assert rows[0]["slug"] == "season-one"
    assert rows[0]["tournament_count"] == 0


@pytest.mark.asyncio
async def test_link_and_match_parsed_populate_event_leaderboard(client):
    event_id = str(uuid4())
    tournament_id = str(uuid4())
    match_id = str(uuid4())

    await handle_integration_event_idempotent("EventCreated", _event_created(event_id))
    await handle_integration_event_idempotent(
        "TournamentCreated", _tournament_created(tournament_id)
    )
    await handle_integration_event_idempotent(
        "TournamentLinkedToEvent",
        TournamentLinkedToEventEvent(
            payload={"tournament_id": tournament_id, "event_id": event_id}
        ).model_dump(mode="json"),
    )
    await handle_integration_event_idempotent(
        "MatchParsed", _match_parsed(match_id, tournament_id)
    )

    detail = client["query"].get(f"/api/v1/queries/events/{event_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["event"]["match_count"] == 1
    assert len(body["tournaments"]) == 1
    assert body["tournaments"][0]["tournament_id"] == tournament_id

    board = client["query"].get(f"/api/v1/queries/events/{event_id}/leaderboard")
    assert board.status_code == 200
    entries = board.json()
    assert len(entries) >= 1
    assert entries[0]["matches_played"] >= 1

    by_class = client["query"].get(
        f"/api/v1/queries/events/{event_id}/leaderboard",
        params={"class_name": "scout"},
    )
    assert by_class.status_code == 200
    assert len(by_class.json()) >= 1

    filtered = client["query"].get(
        "/api/v1/queries/matches", params={"event_id": event_id}
    )
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1


@pytest.mark.asyncio
async def test_unlink_drops_event_matches(client):
    event_id = str(uuid4())
    tournament_id = str(uuid4())
    match_id = str(uuid4())

    await handle_integration_event_idempotent("EventCreated", _event_created(event_id))
    await handle_integration_event_idempotent(
        "TournamentCreated", _tournament_created(tournament_id)
    )
    await handle_integration_event_idempotent(
        "TournamentLinkedToEvent",
        TournamentLinkedToEventEvent(
            payload={"tournament_id": tournament_id, "event_id": event_id}
        ).model_dump(mode="json"),
    )
    await handle_integration_event_idempotent(
        "MatchParsed", _match_parsed(match_id, tournament_id)
    )
    await handle_integration_event_idempotent(
        "TournamentLinkedToEvent",
        TournamentLinkedToEventEvent(
            payload={"tournament_id": tournament_id, "event_id": None}
        ).model_dump(mode="json"),
    )

    detail = client["query"].get(f"/api/v1/queries/events/{event_id}")
    assert detail.status_code == 200
    assert detail.json()["event"]["match_count"] == 0
    assert detail.json()["event"]["tournament_count"] == 0


@pytest.mark.asyncio
async def test_match_tournament_assigned_moves_match(client):
    from_id = str(uuid4())
    to_id = str(uuid4())
    match_id = str(uuid4())

    await handle_integration_event_idempotent(
        "TournamentCreated", _tournament_created(from_id, name="From", slug="from-cup")
    )
    await handle_integration_event_idempotent(
        "TournamentCreated", _tournament_created(to_id, name="To", slug="to-cup")
    )
    await handle_integration_event_idempotent("MatchParsed", _match_parsed(match_id, from_id))
    await handle_integration_event_idempotent(
        "MatchTournamentAssigned",
        MatchTournamentAssignedEvent(
            payload={
                "match_id": match_id,
                "tournament_id": to_id,
                "previous_tournament_id": from_id,
            }
        ).model_dump(mode="json"),
    )

    detail = client["query"].get(f"/api/v1/queries/matches/{match_id}")
    assert detail.status_code == 200
    assert detail.json()["match_summary"]["tournament_id"] == to_id

    tournaments = client["query"].get("/api/v1/queries/tournaments").json()
    by_id = {row["tournament_id"]: row for row in tournaments}
    assert by_id[from_id]["match_count"] == 0
    assert by_id[to_id]["match_count"] == 1
