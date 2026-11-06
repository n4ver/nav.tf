"""Unit tests for the CQRS query service (read routes, validation, errors)."""

from __future__ import annotations

import uuid


def test_health_returns_ok(client):
    response = client["query"].get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["side"] == "query"
    assert body["db_reachable"] is True
    assert "match_count" in body


def test_list_matches_empty_on_fresh_db(client):
    response = client["query"].get("/api/v1/queries/matches")
    assert response.status_code == 200
    assert response.json() == []


def test_get_match_returns_404_for_unknown_id(client):
    response = client["query"].get(f"/api/v1/queries/matches/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Match not found"


def test_list_tournaments_empty_on_fresh_db(client):
    response = client["query"].get("/api/v1/queries/tournaments")
    assert response.status_code == 200
    assert response.json() == []


def test_search_requires_query_string(client):
    response = client["query"].get("/api/v1/queries/search")
    assert response.status_code == 422


def test_search_returns_empty_for_no_matches(client):
    response = client["query"].get(
        "/api/v1/queries/search", params={"q": "nonexistent-player-xyz"}
    )
    assert response.status_code == 200
    assert response.json() == []


def test_player_stats_returns_zeroed_lifetime_for_unknown_player(client):
    response = client["query"].get("/api/v1/queries/players/STEAM_1:1:9999999/stats")
    assert response.status_code == 200
    stats = response.json()
    assert stats["matches_played"] == 0
    assert stats["total_kills"] == 0


def test_leaderboard_returns_empty_for_unknown_tournament(client):
    response = client["query"].get(
        f"/api/v1/queries/tournaments/{uuid.uuid4()}/leaderboard"
    )
    assert response.status_code == 200
    assert response.json() == []


def test_list_benchmarks_on_fresh_db(client):
    response = client["query"].get("/api/v1/queries/benchmarks/class-rating")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_events_empty_on_fresh_db(client):
    response = client["query"].get("/api/v1/queries/events")
    assert response.status_code == 200
    assert response.json() == []


def test_get_event_returns_404_for_unknown_id(client):
    response = client["query"].get(f"/api/v1/queries/events/{uuid.uuid4()}")
    assert response.status_code == 404


def test_event_leaderboard_returns_404_for_unknown_id(client):
    response = client["query"].get(
        f"/api/v1/queries/events/{uuid.uuid4()}/leaderboard"
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"


def test_match_detail_happy_path_after_upload(client):
    upload = client["command"].post(
        "/api/v1/commands/logs/upload",
        json={
            "log_data": (
                "map_name=cp_process_final blu_score=2 red_score=1 duration_seconds=1500 "
                "player steam_id=STEAM_1:1:424242 team=blu class=scout kills=10 deaths=5 assists=2 dpm=350 "
                "player steam_id=STEAM_1:1:67890 team=red class=soldier kills=8 deaths=7 assists=1 dpm=410"
            ),
            "timestamp": "2026-07-28T00:00:00Z",
        },
    )
    assert upload.status_code == 202
    match_id = upload.json()["match_id"]

    summary = client["query"].get("/api/v1/queries/matches")
    assert summary.status_code == 200
    rows = summary.json()
    assert len(rows) == 1
    assert rows[0]["match_id"] == match_id
    assert rows[0]["map_name"] == "cp_process_final"
    assert rows[0]["winning_team"] == "blu"

    detail = client["query"].get(f"/api/v1/queries/matches/{match_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["match_summary"]["match_id"] == match_id
    assert len(body["players"]) == 2


def test_search_finds_player_by_display_name(client):
    client["command"].post(
        "/api/v1/commands/logs/upload",
        json={
            "log_data": (
                "map_name=cp_process_final blu_score=1 red_score=0 "
                "player steam_id=STEAM_1:1:777 team=blu class=scout kills=5 deaths=2 assists=1 dpm=300"
            ),
            "timestamp": "2026-07-28T00:00:00Z",
        },
    )
    client["command"].post(
        "/api/v1/commands/players/display-name",
        json={"steam_id": "STEAM_1:1:777", "display_name": "Searchable Scout"},
    )

    response = client["query"].get(
        "/api/v1/queries/search",
        params={"q": "Searchable"},
    )
    assert response.status_code == 200
    results = response.json()
    assert any(r["display_name"] == "Searchable Scout" for r in results)
