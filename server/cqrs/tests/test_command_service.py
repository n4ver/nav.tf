"""Unit tests for the CQRS command service (auth, validation, happy paths)."""

from __future__ import annotations


def test_health_returns_ok(client):
    response = client["command"].get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["side"] == "command"


def test_upload_requires_bearer_token(raw_client):
    response = raw_client["command"].post(
        "/api/v1/commands/logs/upload",
        json={
            "log_data": "map_name=cp_process_final blu_score=1 red_score=0",
            "timestamp": "2026-07-28T00:00:00Z",
        },
    )
    assert response.status_code == 401
    assert "Not authenticated" in response.json()["detail"]


def test_upload_rejects_invalid_jwt(raw_client):
    response = raw_client["command"].post(
        "/api/v1/commands/logs/upload",
        json={
            "log_data": "map_name=cp_process_final blu_score=1 red_score=0",
            "timestamp": "2026-07-28T00:00:00Z",
        },
        headers={"Authorization": "Bearer not-a-valid-token"},
    )
    assert response.status_code == 401
    assert "Invalid or expired token" in response.json()["detail"]


def test_upload_rejects_non_admin_role(client, player_headers):
    response = client["command"].post(
        "/api/v1/commands/logs/upload",
        json={
            "log_data": "map_name=cp_process_final blu_score=1 red_score=0",
            "timestamp": "2026-07-28T00:00:00Z",
        },
        headers=player_headers,
    )
    assert response.status_code == 403
    assert "Admin role required" in response.json()["detail"]


def test_upload_rejects_empty_log_data(client):
    response = client["command"].post(
        "/api/v1/commands/logs/upload",
        json={"log_data": "   ", "timestamp": "2026-07-28T00:00:00Z"},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_upload_parses_and_accepts_valid_log(client):
    response = client["command"].post(
        "/api/v1/commands/logs/upload",
        json={
            "log_data": (
                "map_name=cp_gorge blu_score=4 red_score=2 duration_seconds=1800 "
                "player steam_id=STEAM_1:1:111 team=blu class=medic kills=2 deaths=3 assists=8 "
                "dpm=120 healing=8500 ubers=4 drops=1"
            ),
            "timestamp": "2026-07-28T00:00:00Z",
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["match_id"]


def test_create_tournament_rejects_invalid_slug(client):
    response = client["command"].post(
        "/api/v1/commands/tournaments",
        json={"name": "Bad Slug Cup", "slug": "Invalid Slug!"},
    )
    assert response.status_code == 400
    assert "slug" in response.json()["detail"].lower()


def test_create_tournament_happy_path(client):
    response = client["command"].post(
        "/api/v1/commands/tournaments",
        json={"name": "Summer Cup", "slug": "summer-cup-2026"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["slug"] == "summer-cup-2026"


def test_auth_me_requires_token(raw_client):
    response = raw_client["command"].get("/api/v1/auth/me")
    assert response.status_code == 401


def test_auth_me_returns_user_for_valid_token(client, admin_headers):
    response = client["command"].get("/api/v1/auth/me", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["steam_id"] == "76561198000000001"
    assert body["role"] == "ADMIN"


def test_ingest_logstf_returns_404_when_log_missing(client, monkeypatch):
    async def fake_fetch_not_found(_self, logstf_id: int):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404, detail=f"logs.tf log not found: {logstf_id}"
        )

    monkeypatch.setattr(
        "cqrs.command_service.app.services.CommandService._fetch_logs_tf_json",
        fake_fetch_not_found,
    )

    response = client["command"].post(
        "/api/v1/commands/logs/ingest-logstf",
        json={"logstf_id": 9999999},
    )
    assert response.status_code == 404


def test_update_display_name_rejects_empty_fields(client):
    response = client["command"].post(
        "/api/v1/commands/players/display-name",
        json={"steam_id": "  ", "display_name": "Name"},
    )
    assert response.status_code == 400

    response = client["command"].post(
        "/api/v1/commands/players/display-name",
        json={"steam_id": "STEAM_1:1:1", "display_name": "  "},
    )
    assert response.status_code == 400


def test_tournament_create_requires_admin(client, player_headers):
    response = client["command"].post(
        "/api/v1/commands/tournaments",
        json={"name": "Player Cup", "slug": "player-cup"},
        headers=player_headers,
    )
    assert response.status_code == 403


def test_create_tournament_duplicate_slug_returns_409(client):
    payload = {"name": "Cup One", "slug": "duplicate-cup"}
    first = client["command"].post("/api/v1/commands/tournaments", json=payload)
    assert first.status_code == 202

    second = client["command"].post(
        "/api/v1/commands/tournaments",
        json={"name": "Cup Two", "slug": "duplicate-cup"},
    )
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"].lower()


def test_update_unknown_tournament_without_claim_fields_returns_404(client):
    import uuid

    response = client["command"].patch(
        f"/api/v1/commands/tournaments/{uuid.uuid4()}",
        json={"name": "Ghost Cup"},
    )
    assert response.status_code == 404


def test_create_event_rejects_invalid_slug(client):
    response = client["command"].post(
        "/api/v1/commands/events",
        json={"name": "Bad Slug Event", "slug": "Invalid Slug!"},
    )
    assert response.status_code == 400
    assert "slug" in response.json()["detail"].lower()


def test_create_event_happy_path(client):
    response = client["command"].post(
        "/api/v1/commands/events",
        json={"name": "Matcha.tf Minicup", "slug": "matcha-tf-minicup"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["slug"] == "matcha-tf-minicup"
    assert body["name"] == "Matcha.tf Minicup"
    assert body["event_id"]


def test_event_create_requires_admin(client, player_headers):
    response = client["command"].post(
        "/api/v1/commands/events",
        json={"name": "Player Event", "slug": "player-event"},
        headers=player_headers,
    )
    assert response.status_code == 403


def test_create_event_duplicate_slug_returns_409(client):
    payload = {"name": "Event One", "slug": "duplicate-event"}
    first = client["command"].post("/api/v1/commands/events", json=payload)
    assert first.status_code == 202

    second = client["command"].post(
        "/api/v1/commands/events",
        json={"name": "Event Two", "slug": "duplicate-event"},
    )
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"].lower()


def test_link_tournament_to_event_happy_path(client):
    event_resp = client["command"].post(
        "/api/v1/commands/events",
        json={"name": "Link Cup Event", "slug": "link-cup-event"},
    )
    assert event_resp.status_code == 202
    event_id = event_resp.json()["event_id"]

    tournament_resp = client["command"].post(
        "/api/v1/commands/tournaments",
        json={"name": "Invite Division", "slug": "invite-division-link"},
    )
    assert tournament_resp.status_code == 202
    tournament_id = tournament_resp.json()["tournament_id"]

    link_resp = client["command"].patch(
        f"/api/v1/commands/tournaments/{tournament_id}/event",
        json={"event_id": event_id},
    )
    assert link_resp.status_code == 202
    body = link_resp.json()
    assert body["status"] == "accepted"
    assert body["tournament_id"] == tournament_id
    assert body["event_id"] == event_id


def test_link_unknown_tournament_returns_404(client):
    import uuid

    event_resp = client["command"].post(
        "/api/v1/commands/events",
        json={"name": "Orphan Link Event", "slug": "orphan-link-event"},
    )
    assert event_resp.status_code == 202
    event_id = event_resp.json()["event_id"]

    response = client["command"].patch(
        f"/api/v1/commands/tournaments/{uuid.uuid4()}/event",
        json={"event_id": event_id},
    )
    assert response.status_code == 404
    assert "tournament" in response.json()["detail"].lower()


def test_link_unknown_event_returns_404(client):
    import uuid

    tournament_resp = client["command"].post(
        "/api/v1/commands/tournaments",
        json={"name": "Unlinked Division", "slug": "unlinked-division"},
    )
    assert tournament_resp.status_code == 202
    tournament_id = tournament_resp.json()["tournament_id"]

    response = client["command"].patch(
        f"/api/v1/commands/tournaments/{tournament_id}/event",
        json={"event_id": str(uuid.uuid4())},
    )
    assert response.status_code == 404
    assert "event" in response.json()["detail"].lower()


def test_create_tournament_with_event_id(client):
    event_resp = client["command"].post(
        "/api/v1/commands/events",
        json={"name": "Linked Create Event", "slug": "linked-create-event"},
    )
    assert event_resp.status_code == 202
    event_id = event_resp.json()["event_id"]

    tournament_resp = client["command"].post(
        "/api/v1/commands/tournaments",
        json={
            "name": "Linked Create Cup",
            "slug": "linked-create-cup",
            "event_id": event_id,
        },
    )
    assert tournament_resp.status_code == 202
    body = tournament_resp.json()
    assert body["event_id"] == event_id


def test_unlink_tournament_from_event(client):
    event_resp = client["command"].post(
        "/api/v1/commands/events",
        json={"name": "Unlink Event", "slug": "unlink-event"},
    )
    event_id = event_resp.json()["event_id"]
    tournament_resp = client["command"].post(
        "/api/v1/commands/tournaments",
        json={"name": "Unlink Cup", "slug": "unlink-cup", "event_id": event_id},
    )
    tournament_id = tournament_resp.json()["tournament_id"]

    unlink = client["command"].patch(
        f"/api/v1/commands/tournaments/{tournament_id}/event",
        json={"event_id": None},
    )
    assert unlink.status_code == 202
    assert unlink.json()["event_id"] is None


def test_upload_with_explicit_tournament_id(client):
    tournament_resp = client["command"].post(
        "/api/v1/commands/tournaments",
        json={"name": "Ingest Cup", "slug": "ingest-cup"},
    )
    tournament_id = tournament_resp.json()["tournament_id"]

    upload = client["command"].post(
        "/api/v1/commands/logs/upload",
        json={
            "log_data": (
                "map_name=cp_process_final blu_score=1 red_score=0 duration_seconds=1200 "
                "player steam_id=STEAM_1:1:555 team=blu class=scout kills=4 deaths=1 assists=1 dpm=200"
            ),
            "timestamp": "2026-07-28T00:00:00Z",
            "tournament_id": tournament_id,
        },
    )
    assert upload.status_code == 202
    match_id = upload.json()["match_id"]

    detail = client["query"].get(f"/api/v1/queries/matches/{match_id}")
    assert detail.status_code == 200
    assert detail.json()["match_summary"]["tournament_id"] == tournament_id


def test_assign_match_tournament(client):
    first = client["command"].post(
        "/api/v1/commands/tournaments",
        json={"name": "From Cup", "slug": "from-cup"},
    )
    second = client["command"].post(
        "/api/v1/commands/tournaments",
        json={"name": "To Cup", "slug": "to-cup"},
    )
    from_id = first.json()["tournament_id"]
    to_id = second.json()["tournament_id"]

    upload = client["command"].post(
        "/api/v1/commands/logs/upload",
        json={
            "log_data": (
                "map_name=cp_granary blu_score=3 red_score=1 duration_seconds=1400 "
                "player steam_id=STEAM_1:1:888 team=blu class=soldier kills=6 deaths=2 assists=2 dpm=280"
            ),
            "timestamp": "2026-07-28T00:00:00Z",
            "tournament_id": from_id,
        },
    )
    match_id = upload.json()["match_id"]

    assigned = client["command"].patch(
        f"/api/v1/commands/matches/{match_id}/tournament",
        json={"tournament_id": to_id},
    )
    assert assigned.status_code == 202
    assert assigned.json()["tournament_id"] == to_id

    detail = client["query"].get(f"/api/v1/queries/matches/{match_id}")
    assert detail.status_code == 200
    assert detail.json()["match_summary"]["tournament_id"] == to_id


def test_update_event_happy_path(client):
    created = client["command"].post(
        "/api/v1/commands/events",
        json={"name": "Rename Me", "slug": "rename-me"},
    )
    assert created.status_code == 202
    event_id = created.json()["event_id"]

    updated = client["command"].patch(
        f"/api/v1/commands/events/{event_id}",
        json={"name": "Season Finals", "slug": "season-finals"},
    )
    assert updated.status_code == 202
    body = updated.json()
    assert body["name"] == "Season Finals"
    assert body["slug"] == "season-finals"

    listing = client["query"].get("/api/v1/queries/events")
    assert listing.status_code == 200
    rows = listing.json()
    assert any(row["slug"] == "season-finals" for row in rows)


def test_update_unknown_event_returns_404(client):
    import uuid

    response = client["command"].patch(
        f"/api/v1/commands/events/{uuid.uuid4()}",
        json={"name": "Ghost Event"},
    )
    assert response.status_code == 404
    assert "event" in response.json()["detail"].lower()


def test_upload_unknown_tournament_returns_404(client):
    import uuid

    response = client["command"].post(
        "/api/v1/commands/logs/upload",
        json={
            "log_data": (
                "map_name=cp_process_final blu_score=1 red_score=0 duration_seconds=1200 "
                "player steam_id=STEAM_1:1:555 team=blu class=scout kills=4 deaths=1 assists=1 dpm=200"
            ),
            "timestamp": "2026-07-28T00:00:00Z",
            "tournament_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 404
    assert "tournament" in response.json()["detail"].lower()
