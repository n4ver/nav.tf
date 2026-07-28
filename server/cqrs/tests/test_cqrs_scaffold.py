import uuid

from cqrs.shared.steam import canonical_steam_id as sid


def test_upload_flow_returns_accepted_and_query_endpoint_lists_match(client):
    steam_id = f"STEAM_1:1:{uuid.uuid4().int % 10_000_000}"
    payload = {
        "log_data": (
            "map_name=cp_process_final blu_score=2 red_score=1 duration_seconds=1500 "
            f"player steam_id={steam_id} team=blu class=scout kills=10 deaths=5 assists=2 dpm=350.5 healing=0 "
            "player steam_id=STEAM_1:1:67890 team=red class=soldier kills=8 deaths=7 assists=1 dpm=410 healing=0"
        ),
        "timestamp": "2026-07-28T00:00:00Z",
    }

    response = client["command"].post("/api/v1/commands/logs/upload", json=payload)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["match_id"]

    query_response = client["query"].get("/api/v1/queries/matches")
    assert query_response.status_code == 200
    matches = query_response.json()
    assert len(matches) == 1
    assert matches[0]["map_name"] == "cp_process_final"
    assert matches[0]["winning_team"] == "blu"

    match_detail = client["query"].get(f"/api/v1/queries/matches/{body['match_id']}")
    assert match_detail.status_code == 200
    detail = match_detail.json()
    assert detail["match_summary"]["match_id"] == body["match_id"]
    assert len(detail["players"]) == 2
    assert detail["match_summary"]["ratings_ready"] is True

    player_stats = client["query"].get(f"/api/v1/queries/players/{steam_id}/stats")
    assert player_stats.status_code == 200
    stats = player_stats.json()
    assert stats["matches_played"] == 1
    assert stats["total_kills"] == 10
    assert stats["average_damage_per_minute"] == 350.5
    assert stats["steam_id"] == sid(steam_id)


def test_empty_log_is_rejected(client):
    response = client["command"].post(
        "/api/v1/commands/logs/upload",
        json={
            "log_data": "   ",
            "timestamp": "2026-07-28T00:00:00Z",
        },
    )
    assert response.status_code == 400


def test_ingest_logstf_fetches_and_projects_match(client, monkeypatch):
    sample = {
        "success": True,
        "info": {"map": "cp_snakewater_final1", "date": 1655389689},
        "teams": {"Blue": {"score": 4}, "Red": {"score": 0}},
        "length": 1868,
        "players": {
            "STEAM_1:1:99999": {
                "team": "Blue",
                "kills": 10,
                "deaths": 5,
                "assists": 2,
                "heal": 0,
                "class_stats": [
                    {
                        "type": "scout",
                        "kills": 10,
                        "deaths": 5,
                        "assists": 2,
                        "dmg": 3500,
                        "total_time": 1800,
                    }
                ],
            }
        },
        "names": {"STEAM_1:1:99999": "Tester"},
    }

    async def fake_fetch(_self, logstf_id: int):
        assert logstf_id == 3209041
        return sample

    monkeypatch.setattr(
        "cqrs.command_service.app.services.CommandService._fetch_logs_tf_json",
        fake_fetch,
    )

    response = client["command"].post(
        "/api/v1/commands/logs/ingest-logstf",
        json={"logstf_id": 3209041},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["log_id"] == 3209041
    assert body["match_id"]

    matches = client["query"].get("/api/v1/queries/matches").json()
    assert len(matches) == 1
    assert matches[0]["map_name"] == "cp_snakewater_final1"
    assert matches[0]["source_log_id"] == 3209041

    retry = client["command"].post(
        "/api/v1/commands/logs/ingest-logstf",
        json={"logstf_id": 3209041},
    )
    assert retry.status_code == 202
    assert retry.json()["status"] == "skipped"


def test_ingest_logstf_maps_404(client, monkeypatch):
    from fastapi import HTTPException

    async def fake_fetch(_self, logstf_id: int):
        raise HTTPException(status_code=404, detail=f"logs.tf log not found: {logstf_id}")

    monkeypatch.setattr(
        "cqrs.command_service.app.services.CommandService._fetch_logs_tf_json",
        fake_fetch,
    )

    response = client["command"].post(
        "/api/v1/commands/logs/ingest-logstf",
        json={"logstf_id": 1},
    )
    assert response.status_code == 404


def test_ingest_cached_log_projects_match(client):
    payload = {
        "log_id": 4037391,
        "tournament_id": 2,
        "section": "R8",
        "data": {
            "info": {"map": "cp_process_final"},
            "teams": {"Blue": {"score": 2}, "Red": {"score": 1}},
            "length": 1500,
            "players": {
                "STEAM_1:1:12345": {
                    "team": "Blue",
                    "kills": 10,
                    "deaths": 5,
                    "assists": 2,
                    "heal": 0,
                    "class_stats": [
                        {
                            "type": "scout",
                            "kills": 10,
                            "deaths": 5,
                            "assists": 2,
                            "dmg": 3505,
                            "total_time": 1500,
                        }
                    ],
                }
            },
        },
    }

    response = client["command"].post("/api/v1/commands/logs/ingest-cached", json=payload)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["match_id"]

    query_response = client["query"].get("/api/v1/queries/matches")
    assert query_response.status_code == 200
    matches = query_response.json()
    assert len(matches) == 1
    assert matches[0]["map_name"] == "cp_process_final"

    tournaments_response = client["query"].get("/api/v1/queries/tournaments")
    assert tournaments_response.status_code == 200
    tournaments = tournaments_response.json()
    assert len(tournaments) == 1
    assert tournaments[0]["name"] == "Qualifier Bracket"
    assert tournaments[0]["slug"] == "qualifier-bracket"
    assert tournaments[0]["match_count"] == 1

    retry = client["command"].post("/api/v1/commands/logs/ingest-cached", json=payload)
    assert retry.status_code == 202
    assert retry.json()["status"] == "skipped"


def test_multiple_rounds_share_one_qualifier_tournament(client):
    for log_id, section in ((4037391, "R8"), (4037381, "R7")):
        response = client["command"].post(
            "/api/v1/commands/logs/ingest-cached",
            json={
                "log_id": log_id,
                "tournament_id": 2,
                "section": section,
                "data": {
                    "info": {"map": f"cp_map_{section.lower()}"},
                    "teams": {"Blue": {"score": 1}, "Red": {"score": 0}},
                    "length": 1200,
                    "players": {},
                },
            },
        )
        assert response.status_code == 202

    tournaments = client["query"].get("/api/v1/queries/tournaments").json()
    assert len(tournaments) == 1
    assert tournaments[0]["name"] == "Qualifier Bracket"
    assert tournaments[0]["match_count"] == 2


def _seed_two_player_match(
    client,
    *,
    log_id: int,
    scout_kills: int = 12,
    soldier_kills: int = 6,
    timestamp: str | None = None,
):
    payload = {
        "log_id": log_id,
        "tournament_id": 2,
        "section": "R8",
        "data": {
            "info": {"map": "cp_process_final"},
            "teams": {"Blue": {"score": 2}, "Red": {"score": 1}},
            "length": 1500,
            "players": {
                "STEAM_1:1:11111": {
                    "team": "Blue",
                    "kills": scout_kills,
                    "deaths": 4,
                    "assists": 3,
                    "heal": 0,
                    "dt": 4200,
                    "hr": 3100,
                    "class_stats": [
                        {
                            "type": "scout",
                            "kills": scout_kills,
                            "deaths": 4,
                            "assists": 3,
                            "dmg": scout_kills * 350,
                            "total_time": 1500,
                            "cpc": 2,
                            "weapon": {"primary": {"acc": 0.42}},
                        }
                    ],
                },
                "STEAM_1:1:22222": {
                    "team": "Red",
                    "kills": soldier_kills,
                    "deaths": 8,
                    "assists": 1,
                    "heal": 0,
                    "dt": 5100,
                    "hr": 2800,
                    "class_stats": [
                        {
                            "type": "soldier",
                            "kills": soldier_kills,
                            "deaths": 8,
                            "assists": 1,
                            "dmg": soldier_kills * 300,
                            "total_time": 1500,
                            "cpc": 1,
                            "weapon": {"primary": {"acc": 0.31}},
                        }
                    ],
                },
            },
        },
    }
    if timestamp:
        payload["timestamp"] = timestamp
    response = client["command"].post("/api/v1/commands/logs/ingest-cached", json=payload)
    assert response.status_code == 202
    return response.json()


def test_upload_is_idempotent_by_content_hash(client):
    payload = {
        "log_data": (
            "map_name=cp_process_final blu_score=2 red_score=1 duration_seconds=1500 "
            "player steam_id=STEAM_1:1:99999 team=blu class=scout kills=10 deaths=5 assists=2 dpm=350 healing=0"
        ),
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

    matches = client["query"].get("/api/v1/queries/matches").json()
    assert len(matches) == 1


def test_leaderboard_ratings_class_breakdown_and_search(client):
    body = _seed_two_player_match(client, log_id=4037400, scout_kills=14, soldier_kills=5)
    tournament_id = client["query"].get("/api/v1/queries/tournaments").json()[0]["tournament_id"]

    leaderboard = client["query"].get(
        f"/api/v1/queries/tournaments/{tournament_id}/leaderboard"
    )
    assert leaderboard.status_code == 200
    entries = leaderboard.json()
    assert len(entries) == 2
    assert entries[0]["average_rating"] >= entries[1]["average_rating"]
    assert {entry["steam_id"] for entry in entries} == {sid("STEAM_1:1:11111"), sid("STEAM_1:1:22222")}

    scout_board = client["query"].get(
        f"/api/v1/queries/tournaments/{tournament_id}/leaderboard",
        params={"class_name": "scout"},
    )
    assert scout_board.status_code == 200
    assert len(scout_board.json()) == 1
    assert scout_board.json()[0]["steam_id"] == sid("STEAM_1:1:11111")

    player = client["query"].get("/api/v1/queries/players/STEAM_1:1:11111/stats").json()
    assert player["matches_played"] == 1
    assert player["average_rating"] > 0
    assert len(player["class_breakdown"]) == 1
    assert player["class_breakdown"][0]["class_name"] == "scout"

    match_detail = client["query"].get(f"/api/v1/queries/matches/{body['match_id']}").json()
    assert all("rating" in row for row in match_detail["players"])

    benchmarks = client["query"].get("/api/v1/queries/benchmarks/class-rating")
    assert benchmarks.status_code == 200
    benchmark_rows = benchmarks.json()
    class_names = {row["class_name"] for row in benchmark_rows}
    assert "scout" in class_names
    assert "soldier" in class_names
    assert all("class_id" in row for row in benchmark_rows)
    assert all("std_rating" in row for row in benchmark_rows)

    by_log = client["query"].get("/api/v1/queries/search", params={"q": "4037400"})
    assert by_log.status_code == 200
    assert by_log.json()[0]["kind"] == "log"
    assert by_log.json()[0]["match_id"] == body["match_id"]

    by_player = client["query"].get("/api/v1/queries/search", params={"q": "STEAM_1:1:11111"})
    assert by_player.status_code == 200
    assert by_player.json()[0]["kind"] == "player"


def test_player_stats_includes_recent_matches(client):
    first = _seed_two_player_match(
        client,
        log_id=4037501,
        scout_kills=11,
        soldier_kills=4,
        timestamp="2026-07-01T12:00:00Z",
    )
    second = _seed_two_player_match(
        client,
        log_id=4037502,
        scout_kills=13,
        soldier_kills=7,
        timestamp="2026-07-02T12:00:00Z",
    )

    player = client["query"].get("/api/v1/queries/players/STEAM_1:1:11111/stats")
    assert player.status_code == 200
    stats = player.json()
    assert stats["matches_played"] == 2
    recent = stats["recent_matches"]
    assert len(recent) == 2
    assert {row["match_id"] for row in recent} == {first["match_id"], second["match_id"]}
    assert all(row["team"] == "blu" for row in recent)
    assert all("rating" in row for row in recent)
    assert all("map_name" in row for row in recent)
    # Newest first by date_played.
    assert recent[0]["match_id"] == second["match_id"]
    assert recent[1]["match_id"] == first["match_id"]


def test_benchmark_rebuild_idempotent(client):
    _seed_two_player_match(client, log_id=4037601, scout_kills=12, soldier_kills=6)

    first = client["query"].get("/api/v1/queries/benchmarks/class-rating")
    assert first.status_code == 200
    first_rows = first.json()
    assert first_rows
    first_by_class = {row["class_id"]: row for row in first_rows}
    first_player = client["query"].get("/api/v1/queries/players/STEAM_1:1:11111/stats").json()

    # Second ingest (distinct payload) triggers another full rebuild_ratings pass.
    _seed_two_player_match(client, log_id=4037602, scout_kills=15, soldier_kills=8)

    second = client["query"].get("/api/v1/queries/benchmarks/class-rating")
    assert second.status_code == 200
    second_rows = second.json()
    second_by_class = {row["class_id"]: row for row in second_rows}

    # No duplicate class_id rows after rebuild.
    assert len(second_rows) == len(second_by_class)
    assert set(first_by_class) == set(second_by_class)

    # Sample size grows with new rows; ratings remain finite and in-range.
    for class_id, before in first_by_class.items():
        after = second_by_class[class_id]
        assert after["sample_size"] >= before["sample_size"]
        assert 0.0 <= after["avg_rating"] <= 2.0

    second_player = client["query"].get("/api/v1/queries/players/STEAM_1:1:11111/stats").json()
    assert second_player["matches_played"] == first_player["matches_played"] + 1
    assert 0.0 <= second_player["average_rating"] <= 2.0


def test_cached_ingest_content_hash_dedup(client):
    log_data = {
        "info": {"map": "cp_process_final"},
        "teams": {"Blue": {"score": 2}, "Red": {"score": 1}},
        "length": 1500,
        "players": {
            "STEAM_1:1:33333": {
                "team": "Blue",
                "kills": 9,
                "deaths": 4,
                "assists": 2,
                "heal": 0,
                "class_stats": [
                    {
                        "type": "scout",
                        "kills": 9,
                        "deaths": 4,
                        "assists": 2,
                        "dmg": 3200,
                        "total_time": 1500,
                    }
                ],
            }
        },
    }

    first = client["command"].post(
        "/api/v1/commands/logs/ingest-cached",
        json={"log_id": 4037701, "tournament_id": 2, "section": "R8", "data": log_data},
    )
    assert first.status_code == 202
    assert first.json()["status"] == "accepted"
    match_id = first.json()["match_id"]

    # Same payload body, different source_log_id — content hash must skip.
    second = client["command"].post(
        "/api/v1/commands/logs/ingest-cached",
        json={"log_id": 4037702, "tournament_id": 2, "section": "R8", "data": log_data},
    )
    assert second.status_code == 202
    assert second.json()["status"] == "skipped"
    assert second.json()["match_id"] == match_id

    matches = client["query"].get("/api/v1/queries/matches").json()
    assert len(matches) == 1


def test_search_multiple_results(client):
    _seed_two_player_match(client, log_id=4037801, scout_kills=10, soldier_kills=5)
    body = _seed_two_player_match(client, log_id=4037802, scout_kills=16, soldier_kills=9)

    # Partial SteamID prefix matches both players.
    response = client["query"].get(
        "/api/v1/queries/search",
        params={"q": "STEAM_1:1:", "limit": 5},
    )
    assert response.status_code == 200
    results = response.json()
    assert len(results) >= 2
    assert all("kind" in row and "id" in row and "label" in row for row in results)
    kinds = {row["kind"] for row in results}
    assert "player" in kinds

    # Exact log ID still returns a typed, ordered result suitable for UI disambiguation.
    by_log = client["query"].get("/api/v1/queries/search", params={"q": "4037802", "limit": 5})
    assert by_log.status_code == 200
    log_results = by_log.json()
    assert len(log_results) >= 1
    assert log_results[0]["kind"] == "log"
    assert log_results[0]["match_id"] == body["match_id"]


def test_async_ratings_ready_after_rebuild_event(client):
    """In-memory broker processes MatchParsed then RatingsRebuildRequested before return."""
    body = _seed_two_player_match(client, log_id=4037901, scout_kills=14, soldier_kills=6)
    match_id = body["match_id"]

    detail = client["query"].get(f"/api/v1/queries/matches/{match_id}").json()
    assert detail["match_summary"]["ratings_ready"] is True
    assert "ratings_ready" in detail["match_summary"]
    assert all(isinstance(row["rating"], (int, float)) for row in detail["players"])
    assert all(row["rating"] > 0 for row in detail["players"])

    list_payload = client["query"].get("/api/v1/queries/matches").json()
    assert list_payload[0]["ratings_ready"] is True


def test_display_name_from_logs_tf_names(client):
    payload = {
        "log_id": 4038101,
        "tournament_id": 2,
        "section": "R8",
        "data": {
            "info": {"map": "cp_process_final"},
            "teams": {"Blue": {"score": 2}, "Red": {"score": 0}},
            "length": 1200,
            "names": {"STEAM_1:1:55555": "Tomahawk"},
            "players": {
                "STEAM_1:1:55555": {
                    "team": "Blue",
                    "kills": 8,
                    "deaths": 3,
                    "assists": 1,
                    "heal": 0,
                    "class_stats": [
                        {
                            "type": "scout",
                            "kills": 8,
                            "deaths": 3,
                            "assists": 1,
                            "dmg": 2800,
                            "total_time": 1200,
                        }
                    ],
                }
            },
        },
    }
    response = client["command"].post("/api/v1/commands/logs/ingest-cached", json=payload)
    assert response.status_code == 202
    match_id = response.json()["match_id"]

    detail = client["query"].get(f"/api/v1/queries/matches/{match_id}").json()
    assert detail["players"][0]["display_name"] == "Tomahawk"

    player = client["query"].get("/api/v1/queries/players/STEAM_1:1:55555/stats").json()
    assert player["display_name"] == "Tomahawk"

    tournament_id = client["query"].get("/api/v1/queries/tournaments").json()[0]["tournament_id"]
    board = client["query"].get(
        f"/api/v1/queries/tournaments/{tournament_id}/leaderboard"
    ).json()
    assert board[0]["display_name"] == "Tomahawk"


def test_upload_uses_stable_default_tournament_id(client):
    from cqrs.shared.tournaments import stable_tournament_uuid_from_slug

    expected = str(stable_tournament_uuid_from_slug("default-tournament"))
    payloads = [
        {
            "log_data": (
                "map_name=cp_process_final blu_score=2 red_score=1 duration_seconds=1500 "
                "player steam_id=STEAM_1:1:90001 team=blu class=scout kills=10 deaths=5 assists=2 dpm=350 healing=0"
            ),
            "timestamp": "2026-07-10T00:00:00Z",
        },
        {
            "log_data": (
                "map_name=cp_gullywash_final1 blu_score=1 red_score=2 duration_seconds=1400 "
                "player steam_id=STEAM_1:1:90002 team=red class=soldier kills=9 deaths=6 assists=1 dpm=400 healing=0"
            ),
            "timestamp": "2026-07-11T00:00:00Z",
        },
    ]
    match_ids = []
    for payload in payloads:
        response = client["command"].post("/api/v1/commands/logs/upload", json=payload)
        assert response.status_code == 202
        match_ids.append(response.json()["match_id"])

    details = [
        client["query"].get(f"/api/v1/queries/matches/{match_id}").json()
        for match_id in match_ids
    ]
    tournament_ids = {detail["match_summary"]["tournament_id"] for detail in details}
    assert tournament_ids == {expected}

    tournaments = client["query"].get("/api/v1/queries/tournaments").json()
    default_rows = [row for row in tournaments if row["slug"] == "default-tournament"]
    assert len(default_rows) == 1
    assert default_rows[0]["tournament_id"] == expected


def test_leaderboard_reads_from_snapshot(client):
    body = _seed_two_player_match(client, log_id=4038001, scout_kills=18, soldier_kills=5)
    tournament_id = client["query"].get("/api/v1/queries/tournaments").json()[0]["tournament_id"]

    leaderboard = client["query"].get(
        f"/api/v1/queries/tournaments/{tournament_id}/leaderboard"
    )
    assert leaderboard.status_code == 200
    entries = leaderboard.json()
    assert len(entries) == 2
    assert entries[0]["average_rating"] >= entries[1]["average_rating"]

    scout_board = client["query"].get(
        f"/api/v1/queries/tournaments/{tournament_id}/leaderboard",
        params={"class_name": "scout"},
    )
    assert scout_board.status_code == 200
    assert len(scout_board.json()) == 1
    assert scout_board.json()[0]["steam_id"] == sid("STEAM_1:1:11111")

    empty = client["query"].get(
        "/api/v1/queries/tournaments/00000000-0000-0000-0000-000000000000/leaderboard"
    )
    assert empty.status_code == 200
    assert empty.json() == []

    # Second rebuild must not duplicate snapshot rows for the same players.
    _seed_two_player_match(client, log_id=4038002, scout_kills=20, soldier_kills=7)
    again = client["query"].get(
        f"/api/v1/queries/tournaments/{tournament_id}/leaderboard"
    ).json()
    steam_ids = [row["steam_id"] for row in again]
    assert len(steam_ids) == len(set(steam_ids))
    assert body["match_id"]
