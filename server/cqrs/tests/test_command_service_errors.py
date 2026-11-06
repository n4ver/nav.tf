"""Additional command-service error-path and update tests."""

from __future__ import annotations


def test_upload_skips_duplicate_log_content(client):
    payload = {
        "log_data": "map_name=cp_dulplicate_test blu_score=1 red_score=0 duration_seconds=900",
        "timestamp": "2026-07-28T00:00:00Z",
    }
    first = client["command"].post("/api/v1/commands/logs/upload", json=payload)
    assert first.status_code == 202
    assert first.json()["status"] == "accepted"
    match_id = first.json()["match_id"]

    second = client["command"].post("/api/v1/commands/logs/upload", json=payload)
    assert second.status_code == 202
    assert second.json()["status"] == "skipped"
    assert second.json()["match_id"] == match_id


def test_ingest_cached_missing_log_returns_404(client, monkeypatch):
    def _missing(_log_id: int, *, cache_path=None):
        raise KeyError(f"log_id {_log_id} not found")

    monkeypatch.setattr(
        "cqrs.command_service.app.services.get_cached_log_data", _missing
    )

    response = client["command"].post(
        "/api/v1/commands/logs/ingest-cached",
        json={"log_id": 999888777, "tournament_id": 2, "section": "missing"},
    )
    assert response.status_code == 404


def test_ingest_logstf_network_failure_returns_502(client, monkeypatch):
    async def fake_fetch(_self, _logstf_id: int):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=502, detail="Failed to reach logs.tf: connection refused"
        )

    monkeypatch.setattr(
        "cqrs.command_service.app.services.CommandService._fetch_logs_tf_json",
        fake_fetch,
    )

    response = client["command"].post(
        "/api/v1/commands/logs/ingest-logstf",
        json={"logstf_id": 1234567},
    )
    assert response.status_code == 502
    assert "logs.tf" in response.json()["detail"].lower()


def test_ingest_logstf_invalid_json_returns_502(client, monkeypatch):
    async def fake_fetch(_self, _logstf_id: int):
        from fastapi import HTTPException

        raise HTTPException(status_code=502, detail="logs.tf returned invalid JSON")

    monkeypatch.setattr(
        "cqrs.command_service.app.services.CommandService._fetch_logs_tf_json",
        fake_fetch,
    )

    response = client["command"].post(
        "/api/v1/commands/logs/ingest-logstf",
        json={"logstf_id": 1234568},
    )
    assert response.status_code == 502


def test_update_tournament_renames_existing_record(client):
    create = client["command"].post(
        "/api/v1/commands/tournaments",
        json={"name": "Original Cup", "slug": "rename-me-cup"},
    )
    assert create.status_code == 202
    tournament_id = create.json()["tournament_id"]

    patch = client["command"].patch(
        f"/api/v1/commands/tournaments/{tournament_id}",
        json={"name": "Renamed Cup"},
    )
    assert patch.status_code == 202
    assert patch.json()["name"] == "Renamed Cup"

    listed = client["query"].get("/api/v1/queries/tournaments").json()
    assert any(row["name"] == "Renamed Cup" for row in listed)


def test_update_tournament_rejects_empty_name(client):
    create = client["command"].post(
        "/api/v1/commands/tournaments",
        json={"name": "Name Guard Cup", "slug": "name-guard-cup"},
    )
    tournament_id = create.json()["tournament_id"]

    response = client["command"].patch(
        f"/api/v1/commands/tournaments/{tournament_id}",
        json={"name": "   "},
    )
    assert response.status_code == 400


def test_steam_callback_redirects_with_error(client, monkeypatch):
    async def fake_validate(_self, _params):
        raise ValueError("OpenID validation failed")

    monkeypatch.setattr(
        "cqrs.command_service.app.main.SteamOpenIdClient.validate_callback",
        fake_validate,
    )

    response = client["command"].get(
        "/api/v1/auth/steam/callback",
        params={"openid.mode": "id_res"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "error=" in response.headers["location"]


def test_steam_callback_success_redirects_with_code(client, monkeypatch):
    async def fake_validate(_self, _params):
        return "76561198000000099"

    async def fake_upsert(_self, steam_id: str):
        from cqrs.command_service.app.models import User
        from cqrs.shared.auth import UserRole
        from cqrs.shared.timeutils import utcnow

        now = utcnow()
        return User(
            steam_id=steam_id,
            display_name="Callback User",
            role=UserRole.ADMIN,
            created_at=now,
            updated_at=now,
            last_login_at=now,
        )

    monkeypatch.setattr(
        "cqrs.command_service.app.main.SteamOpenIdClient.validate_callback",
        fake_validate,
    )
    monkeypatch.setattr(
        "cqrs.command_service.app.main.AuthService.upsert_steam_user",
        fake_upsert,
    )

    response = client["command"].get(
        "/api/v1/auth/steam/callback",
        params={"openid.mode": "id_res"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "code=" in response.headers["location"]
