"""Admin proxy from the command service to the api-consumer (matcha.tf ingest)."""

from __future__ import annotations

import json

import httpx
import pytest

from cqrs.command_service.app import api_consumer

BASE_URL = "http://api-consumer.test:8010"
API_KEY = "test-consumer-key"


@pytest.fixture
def consumer(monkeypatch):
    """Route the proxy's outbound httpx calls to an in-test handler and record them."""
    state: dict[str, object] = {"requests": [], "handler": None}

    def transport_handler(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)  # type: ignore[union-attr]
        handler = state["handler"]
        assert handler is not None, "test did not set a consumer handler"
        return handler(request)  # type: ignore[operator]

    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(transport_handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(api_consumer.httpx, "AsyncClient", client_factory)
    monkeypatch.setenv("API_CONSUMER_URL", BASE_URL)
    monkeypatch.setenv("API_CONSUMER_API_KEY", API_KEY)
    return state


def test_ingest_match_forwards_with_the_api_key(client, consumer):
    consumer["handler"] = lambda _req: httpx.Response(
        202,
        json={"status": "accepted", "accepted": 2, "skipped": 0, "published": [{"matchId": "m-1"}]},
    )

    response = client["command"].post(
        "/api/v1/commands/sources/matcha/matches", json={"match_id": 201}
    )

    assert response.status_code == 202
    assert response.json()["accepted"] == 2
    [request] = consumer["requests"]
    assert str(request.url) == f"{BASE_URL}/webhooks/matcha/match"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    assert json.loads(request.content) == {"matchId": 201}


def test_poll_passes_reset_flag(client, consumer):
    consumer["handler"] = lambda _req: httpx.Response(202, json={"status": "accepted", "matchIds": 4})

    response = client["command"].post(
        "/api/v1/commands/sources/matcha/poll", json={"reset": True}
    )

    assert response.status_code == 202
    assert response.json()["matchIds"] == 4
    [request] = consumer["requests"]
    assert request.url.path == "/admin/poll"
    assert request.url.params["reset"] == "true"


def test_poll_without_reset_sends_no_query(client, consumer):
    consumer["handler"] = lambda _req: httpx.Response(202, json={"status": "accepted"})

    client["command"].post("/api/v1/commands/sources/matcha/poll", json={})

    [request] = consumer["requests"]
    assert "reset" not in request.url.params


def test_poll_in_progress_maps_to_409(client, consumer):
    consumer["handler"] = lambda _req: httpx.Response(
        409, json={"status": "busy", "error": "Poll already in progress"}
    )

    response = client["command"].post("/api/v1/commands/sources/matcha/poll", json={})

    assert response.status_code == 409
    assert response.json()["detail"] == "Poll already in progress"


def test_upstream_failure_maps_to_502(client, consumer):
    consumer["handler"] = lambda _req: httpx.Response(
        502, json={"status": "failed", "error": "All 2 logs.tf fetches failed for match 9"}
    )

    response = client["command"].post(
        "/api/v1/commands/sources/matcha/matches", json={"match_id": 9}
    )

    assert response.status_code == 502
    assert "logs.tf fetches failed" in response.json()["detail"]


def test_rejected_key_is_reported_as_unavailable(client, consumer):
    consumer["handler"] = lambda _req: httpx.Response(401, json={"error": "Unauthorized"})

    response = client["command"].post(
        "/api/v1/commands/sources/matcha/matches", json={"match_id": 9}
    )

    assert response.status_code == 503
    assert "Unauthorized" in response.json()["detail"]


def test_unreachable_consumer_returns_503(client, consumer):
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    consumer["handler"] = refuse

    response = client["command"].post("/api/v1/commands/sources/matcha/poll", json={})

    assert response.status_code == 503
    assert response.json()["detail"] == "api-consumer is unreachable"


def test_timeout_returns_504(client, consumer):
    def slow(request):
        raise httpx.ReadTimeout("timed out", request=request)

    consumer["handler"] = slow

    response = client["command"].post("/api/v1/commands/sources/matcha/poll", json={})

    assert response.status_code == 504


def test_unconfigured_consumer_returns_503(client, monkeypatch):
    monkeypatch.delenv("API_CONSUMER_URL", raising=False)

    response = client["command"].post(
        "/api/v1/commands/sources/matcha/matches", json={"match_id": 1}
    )

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_api_key_falls_back_to_webhook_api_key(monkeypatch):
    monkeypatch.delenv("API_CONSUMER_API_KEY", raising=False)
    monkeypatch.setenv("WEBHOOK_API_KEY", "shared-key")

    assert api_consumer.api_consumer_api_key() == "shared-key"


def test_invalid_match_id_is_rejected(client, consumer):
    response = client["command"].post(
        "/api/v1/commands/sources/matcha/matches", json={"match_id": 0}
    )

    assert response.status_code == 422
    assert consumer["requests"] == []


def test_status_reports_reachability(client, consumer, admin_headers):
    consumer["handler"] = lambda _req: httpx.Response(200, json={"status": "ok"})

    response = client["command"].get(
        "/api/v1/commands/sources/matcha/status", headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json() == {"configured": True, "reachable": True, "source_site": "matcha.tf"}


def test_status_when_unconfigured(client, monkeypatch, admin_headers):
    monkeypatch.delenv("API_CONSUMER_URL", raising=False)

    response = client["command"].get(
        "/api/v1/commands/sources/matcha/status", headers=admin_headers
    )

    assert response.json()["configured"] is False
    assert response.json()["reachable"] is False


def test_matcha_routes_require_admin(raw_client, player_headers):
    for path, body in (
        ("/api/v1/commands/sources/matcha/matches", {"match_id": 1}),
        ("/api/v1/commands/sources/matcha/poll", {}),
    ):
        anonymous = raw_client["command"].post(path, json=body)
        player = raw_client["command"].post(path, json=body, headers=player_headers)
        assert anonymous.status_code == 401
        assert player.status_code == 403

    status_resp = raw_client["command"].get(
        "/api/v1/commands/sources/matcha/status", headers=player_headers
    )
    assert status_resp.status_code == 403
