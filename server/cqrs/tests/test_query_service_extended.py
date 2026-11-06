"""Additional query-service route coverage."""

from __future__ import annotations


def test_list_matches_respects_limit(client):
    for idx in range(3):
        client["command"].post(
            "/api/v1/commands/logs/upload",
            json={
                "log_data": (
                    f"map_name=cp_limit_test_{idx} blu_score=1 red_score=0 "
                    f"player steam_id=STEAM_1:1:{1000 + idx} team=blu class=scout "
                    f"kills=1 deaths=0 assists=0 dpm=100"
                ),
                "timestamp": "2026-07-28T00:00:00Z",
            },
        )

    response = client["query"].get("/api/v1/queries/matches", params={"limit": 2})
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_search_finds_match_by_uuid(client):
    upload = client["command"].post(
        "/api/v1/commands/logs/upload",
        json={
            "log_data": (
                "map_name=cp_search_uuid blu_score=2 red_score=1 "
                "player steam_id=STEAM_1:1:8888 team=blu class=scout kills=3 deaths=1 assists=0 dpm=200"
            ),
            "timestamp": "2026-07-28T00:00:00Z",
        },
    )
    match_id = upload.json()["match_id"]

    response = client["query"].get("/api/v1/queries/search", params={"q": match_id})
    assert response.status_code == 200
    results = response.json()
    assert any(row["kind"] == "match" and row["id"] == match_id for row in results)


def test_leaderboard_supports_class_filter(client):
    client["command"].post(
        "/api/v1/commands/logs/upload",
        json={
            "log_data": (
                "map_name=cp_leaderboard blu_score=3 red_score=1 duration_seconds=1200 "
                "player steam_id=STEAM_1:1:5555 team=blu class=medic kills=1 deaths=2 assists=10 dpm=80 healing=9000 ubers=3"
            ),
            "timestamp": "2026-07-28T00:00:00Z",
        },
    )

    tournaments = client["query"].get("/api/v1/queries/tournaments").json()
    assert tournaments
    tournament_id = tournaments[0]["tournament_id"]

    all_classes = client["query"].get(
        f"/api/v1/queries/tournaments/{tournament_id}/leaderboard",
        params={"limit": 10},
    )
    medic_only = client["query"].get(
        f"/api/v1/queries/tournaments/{tournament_id}/leaderboard",
        params={"class_name": "medic", "limit": 10},
    )
    assert all_classes.status_code == 200
    assert medic_only.status_code == 200
    if medic_only.json():
        assert all(row["primary_class"] == "medic" for row in medic_only.json())
