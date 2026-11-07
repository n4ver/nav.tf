"""Built-in tournaments (catalog brackets, default) only exist in the read model
until an admin manages them; command endpoints must accept their ids."""

from __future__ import annotations

from cqrs.shared.tournaments import (
    DEFAULT_TOURNAMENT_SLUG,
    builtin_tournament_command,
    stable_tournament_uuid,
    stable_tournament_uuid_from_slug,
)

QUALIFIER_ID = str(stable_tournament_uuid(2))


def _ingest_qualifier_log(client, log_id: int) -> str:
    response = client["command"].post(
        "/api/v1/commands/logs/ingest-cached",
        json={
            "log_id": log_id,
            "tournament_id": 2,
            "section": "R8",
            "data": {
                "info": {"map": f"cp_map_{log_id}"},
                "teams": {"Blue": {"score": 1}, "Red": {"score": 0}},
                "length": 1200,
                "players": {},
            },
        },
    )
    assert response.status_code == 202, response.text
    return response.json()["match_id"]


def _create_event(client, slug: str) -> str:
    response = client["command"].post(
        "/api/v1/commands/events", json={"name": slug.title(), "slug": slug}
    )
    assert response.status_code == 202, response.text
    return response.json()["event_id"]


def _query_tournament(client, tournament_id: str) -> dict:
    rows = client["query"].get("/api/v1/queries/tournaments").json()
    return next(row for row in rows if row["tournament_id"] == tournament_id)


def test_builtin_lookup_covers_catalog_and_default_only():
    assert builtin_tournament_command(QUALIFIER_ID).slug == "qualifier-bracket"
    default_id = str(stable_tournament_uuid_from_slug(DEFAULT_TOURNAMENT_SLUG))
    assert builtin_tournament_command(default_id).slug == DEFAULT_TOURNAMENT_SLUG
    assert builtin_tournament_command("00000000-0000-0000-0000-000000000000") is None


def test_link_ingested_catalog_tournament_to_event(client):
    _ingest_qualifier_log(client, 4100001)
    event_id = _create_event(client, "builtin-link-event")

    response = client["command"].patch(
        f"/api/v1/commands/tournaments/{QUALIFIER_ID}/event",
        json={"event_id": event_id},
    )
    assert response.status_code == 202, response.text
    assert _query_tournament(client, QUALIFIER_ID)["event_id"] == event_id


def test_later_ingest_keeps_the_event_link(client):
    _ingest_qualifier_log(client, 4100002)
    event_id = _create_event(client, "builtin-keep-event")
    client["command"].patch(
        f"/api/v1/commands/tournaments/{QUALIFIER_ID}/event",
        json={"event_id": event_id},
    )

    _ingest_qualifier_log(client, 4100003)
    row = _query_tournament(client, QUALIFIER_ID)
    assert row["event_id"] == event_id
    assert row["match_count"] == 2


def test_assign_match_to_builtin_tournament(client):
    match_id = _ingest_qualifier_log(client, 4100004)
    invite_id = str(stable_tournament_uuid(1))
    response = client["command"].patch(
        f"/api/v1/commands/matches/{match_id}/tournament",
        json={"tournament_id": invite_id},
    )
    assert response.status_code == 202, response.text


def test_upload_into_builtin_tournament(client):
    response = client["command"].post(
        "/api/v1/commands/logs/upload",
        json={
            "log_data": "map_name=cp_process_final blu_score=1 red_score=0",
            "timestamp": "2026-07-28T00:00:00Z",
            "tournament_id": QUALIFIER_ID,
        },
    )
    assert response.status_code == 202, response.text
