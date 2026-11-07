"""Leaderboard across every tournament (the home page's "All events / All matches" scope)."""

from __future__ import annotations


def _upload(client, *, steam_id: str, class_name: str, tournament_id: str | None = None) -> None:
    payload: dict[str, object] = {
        "log_data": (
            f"map_name=cp_global_{steam_id[-4:]} blu_score=3 red_score=1 duration_seconds=1200 "
            f"player steam_id={steam_id} team=blu class={class_name} "
            "kills=10 deaths=2 assists=4 dpm=250"
        ),
        "timestamp": "2026-07-28T00:00:00Z",
    }
    if tournament_id:
        payload["tournament_id"] = tournament_id
    response = client["command"].post("/api/v1/commands/logs/upload", json=payload)
    assert response.status_code == 202


def test_global_leaderboard_is_empty_without_matches(client):
    response = client["query"].get("/api/v1/queries/leaderboard")

    assert response.status_code == 200
    assert response.json() == []


def test_global_leaderboard_spans_every_tournament(client):
    created = client["command"].post(
        "/api/v1/commands/tournaments",
        json={"name": "Global Cup", "slug": "global-cup"},
    )
    assert created.status_code == 202
    cup_id = created.json()["tournament_id"]

    _upload(client, steam_id="STEAM_1:1:7101", class_name="scout")
    _upload(client, steam_id="STEAM_1:1:7202", class_name="soldier", tournament_id=cup_id)

    tournament_rows = client["query"].get(
        f"/api/v1/queries/tournaments/{cup_id}/leaderboard"
    ).json()
    global_rows = client["query"].get("/api/v1/queries/leaderboard").json()

    assert len(tournament_rows) == 1
    assert len(global_rows) == 2
    ratings = [row["average_rating"] for row in global_rows]
    assert ratings == sorted(ratings, reverse=True)


def test_global_leaderboard_filters_by_class_and_limit(client):
    _upload(client, steam_id="STEAM_1:1:7303", class_name="scout")
    _upload(client, steam_id="STEAM_1:1:7404", class_name="soldier")

    scouts = client["query"].get(
        "/api/v1/queries/leaderboard", params={"class_name": "scout"}
    ).json()
    limited = client["query"].get("/api/v1/queries/leaderboard", params={"limit": 1}).json()

    assert scouts and all(row["primary_class"] == "scout" for row in scouts)
    assert len(limited) == 1


def test_global_leaderboard_rejects_out_of_range_limit(client):
    response = client["query"].get("/api/v1/queries/leaderboard", params={"limit": 0})

    assert response.status_code == 422
