"""Auth / RBAC tests for Steam OpenID + JWT command protection."""

from __future__ import annotations

from cqrs.shared.auth import UserRole, create_access_token, decode_access_token
from cqrs.shared.auth.steam_openid import extract_steam_id_from_claimed_id
from cqrs.shared.steam import canonical_steam_id


def test_jwt_embeds_steam_id_and_role():
    token = create_access_token(
        steam_id="76561198000000001",
        role=UserRole.ADMIN,
        display_name="Admin",
    )
    claims = decode_access_token(token)
    assert claims["steam_id"] == "76561198000000001"
    assert claims["role"] == "ADMIN"
    assert claims["sub"] == "76561198000000001"


def test_extract_steam_id_from_claimed_id():
    steam_id = extract_steam_id_from_claimed_id(
        "https://steamcommunity.com/openid/id/76561198000000001"
    )
    assert steam_id == "76561198000000001"
    assert extract_steam_id_from_claimed_id("not-a-steam-url") is None


def test_upload_requires_auth(client):
    response = client["command"].post(
        "/api/v1/commands/logs/upload",
        json={
            "log_data": "map_name=cp_process_final blu_score=1 red_score=0",
            "timestamp": "2026-07-28T00:00:00Z",
        },
        headers={"Authorization": "Bearer not-a-valid-token"},
    )
    assert response.status_code == 401


def test_upload_rejects_player_role(client, player_headers):
    response = client["command"].post(
        "/api/v1/commands/logs/upload",
        json={
            "log_data": "map_name=cp_process_final blu_score=1 red_score=0",
            "timestamp": "2026-07-28T00:00:00Z",
        },
        headers=player_headers,
    )
    assert response.status_code == 403


def test_ingest_logstf_rejects_player_role(client, player_headers):
    response = client["command"].post(
        "/api/v1/commands/logs/ingest-logstf",
        json={"logstf_id": 3209041},
        headers=player_headers,
    )
    assert response.status_code == 403


def test_seed_service_token_allows_ingest(client, monkeypatch):
    monkeypatch.setenv("SEED_SERVICE_TOKEN", "test-seed-token")
    response = client["command"].post(
        "/api/v1/commands/logs/ingest-cached",
        json={"log_id": 4037391, "tournament_id": 2, "section": "probe"},
        headers={"Authorization": "Bearer test-seed-token"},
    )
    # Missing cache entry is fine — auth must pass (404), not 401/403.
    assert response.status_code in {202, 404}
    assert response.status_code not in {401, 403}


def test_steam_login_redirects(client):
    response = client["command"].get("/api/v1/auth/steam/login", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    assert "steamcommunity.com/openid/login" in location
    assert "openid.return_to=" in location
    # Callback must stay on HTTP dev frontend port, not bare :8001 (causes ERR_SSL_PROTOCOL_ERROR).
    assert "localhost%3A8001" not in location
    assert "https%3A%2F%2Flocalhost" not in location.lower()


def test_steam_login_uses_forwarded_host(client):
    response = client["command"].get(
        "/api/v1/auth/steam/login",
        follow_redirects=False,
        headers={
            "X-Forwarded-Host": "localhost:5173",
            "X-Forwarded-Proto": "http",
        },
    )
    assert response.status_code == 302
    location = response.headers["location"]
    assert "openid.return_to=http%3A%2F%2Flocalhost%3A5173" in location


def test_admin_can_create_tournament_and_query_lists_it(client):
    create = client["command"].post(
        "/api/v1/commands/tournaments",
        json={"name": "Custom Cup", "slug": "custom-cup"},
    )
    assert create.status_code == 202
    body = create.json()
    assert body["status"] == "accepted"
    assert body["slug"] == "custom-cup"

    tournaments = client["query"].get("/api/v1/queries/tournaments")
    assert tournaments.status_code == 200
    rows = tournaments.json()
    assert any(row["slug"] == "custom-cup" for row in rows)


def test_admin_can_update_player_alias(client):
    steam_id = "STEAM_1:1:424242"
    upload = client["command"].post(
        "/api/v1/commands/logs/upload",
        json={
            "log_data": (
                "map_name=cp_process_final blu_score=2 red_score=1 duration_seconds=1500 "
                f"player steam_id={steam_id} team=blu class=scout kills=10 deaths=5 assists=2 dpm=350.5 healing=0 "
                "player steam_id=STEAM_1:1:67890 team=red class=soldier kills=8 deaths=7 assists=1 dpm=410 healing=0"
            ),
            "timestamp": "2026-07-28T00:00:00Z",
        },
    )
    assert upload.status_code == 202

    alias = client["command"].post(
        "/api/v1/commands/players/display-name",
        json={"steam_id": steam_id, "display_name": "Alias Ace"},
    )
    assert alias.status_code == 202

    stats = client["query"].get(f"/api/v1/queries/players/{steam_id}/stats")
    assert stats.status_code == 200
    assert stats.json()["display_name"] == "Alias Ace"
    assert stats.json()["steam_id"] == canonical_steam_id(steam_id)


def test_auth_me_returns_claims(client, admin_headers):
    response = client["command"].get("/api/v1/auth/me", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["steam_id"] == "76561198000000001"
    assert body["role"] == "ADMIN"


def test_auth_exchange_rejects_invalid_code(client):
    response = client["command"].post(
        "/api/v1/auth/exchange",
        json={"code": "not-a-valid-code"},
    )
    assert response.status_code == 401


def test_auth_code_exchange_single_use():
    import asyncio

    from cqrs.command_service.app.auth_service import AuthService
    from cqrs.command_service.app.db import SessionLocal

    async def run() -> None:
        async with SessionLocal() as session:
            auth = AuthService(session)
            token = create_access_token(
                steam_id=ADMIN_STEAM_ID,
                role=UserRole.ADMIN,
                display_name="Test Admin",
            )
            code = await auth.create_login_code(token)
            assert await auth.exchange_login_code(code) == token

            try:
                await auth.exchange_login_code(code)
            except ValueError as exc:
                assert "expired" in str(exc).lower() or "invalid" in str(exc).lower()
            else:
                raise AssertionError("Expected reused auth code to be rejected")

    asyncio.run(run())
