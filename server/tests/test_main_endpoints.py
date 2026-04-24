from fastapi.testclient import TestClient
from fastapi import BackgroundTasks
import asyncio
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import main # type: ignore
from models import Match, MatchStat, Player, Class, Tournament, seed_classes # type: ignore


client = TestClient(main.app)


def build_test_client_with_db() -> tuple[TestClient, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def initialize_database() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)
        async with async_session_factory() as session:
            await seed_classes(session)

    asyncio.run(initialize_database())

    async def get_test_session():
        async with async_session_factory() as session:
            yield session

    main.app.dependency_overrides[main.get_session] = get_test_session
    return TestClient(main.app), async_session_factory


def test_root_endpoint_returns_hello_world() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"Hello": "World"}


def test_ingest_log_returns_job_response_and_schedules_task(monkeypatch) -> None:
    called = {}

    class RecordingBackgroundTasks(BackgroundTasks):
        def add_task(self, func, *args, **kwargs):
            called["func"] = func
            called["args"] = args
            called["kwargs"] = kwargs

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(main.asyncio, "sleep", no_sleep)

    async def run_test() -> None:
        result = await main.ingest_log(
            log_id=76543,
            tournament_id=9,
            background_tasks=RecordingBackgroundTasks(),
        )

        assert result == {
            "message": "Ingestion for log 76543 started.",
            "job_id": 76543,
        }

    asyncio.run(run_test())

    assert called["func"] is main.fetch_and_process_log
    assert called["args"] == (76543, 9)
    assert called["kwargs"] == {}


def test_logs_status_returns_404_for_unknown_job() -> None:
    response = client.get("/logs/status/999999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found"}

def test_get_log_job_status_success() -> None:
    job_id = 12345
    main.JOB_STATUS[job_id] = {
        "job_id": job_id,
        "status": "completed",
        "detail": None,
        "updated_at": "2023-01-01T00:00:00Z",
    }
    try:
        response = client.get(f"/logs/status/{job_id}")
        assert response.status_code == 200
        assert response.json() == main.JOB_STATUS[job_id]
    finally:
        del main.JOB_STATUS[job_id]

def test_health_endpoint_returns_ok() -> None:
    test_client, engine = build_test_client_with_db()
    try:
        response = test_client.get("/health/")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    finally:
        main.app.dependency_overrides.clear()


def test_log_stats_endpoint_returns_match_stats() -> None:
    test_client, session_factory = build_test_client_with_db()
    try:
        async def seed_data() -> None:
            async with session_factory() as test_session:
                player = Player(steamid="steam_abc", last_known_name="MedicMain")
                test_session.add(player)
                await test_session.commit()
                await test_session.refresh(player)

                match = Match(log_id=24680, map="cp_process", tournament_id=1)
                test_session.add(match)
                await test_session.commit()
                await test_session.refresh(match)

                stat = MatchStat(
                    match_id=match.id, # type: ignore
                    player_id=player.id, # type: ignore
                    class_id=6,
                    team="Blue",
                    playtime=1200,
                    kills=10,
                    deaths=4,
                    dpm=300.0,
                    primary_accuracy=45.5,
                    damage_dealt=6000,
                    damage_received=4200,
                    heals_received=5000,
                    headshots=0,
                    backstabs=0,
                    airshots=0,
                    captures=3,
                )
                test_session.add(stat)
                await test_session.commit()

        asyncio.run(seed_data())

        response = test_client.get("/logs/24680/stats")
        assert response.status_code == 200

        payload = response.json()
        assert payload["log_id"] == 24680
        assert payload["map"] == "cp_process"
        assert payload["summary"] == {
            "entries": 1,
            "total_kills": 10,
            "total_deaths": 4,
            "avg_dpm": 300.0,
        }
        assert payload["stats"][0]["steamid"] == "steam_abc"
        assert payload["stats"][0]["class"] == "Medic"
    finally:
        main.app.dependency_overrides.clear()


def test_leaderboard_supports_sort_by_kad() -> None:
    test_client, session_factory = build_test_client_with_db()
    try:
        async def seed_data() -> None:
            async with session_factory() as test_session:
                tournament = Tournament(id=7, name="Invite")
                test_session.add(tournament)

                scout = Player(steamid="steam_scout", last_known_name="Scout")
                soldier = Player(steamid="steam_soldier", last_known_name="Soldier")
                test_session.add(scout)
                test_session.add(soldier)
                await test_session.commit()
                await test_session.refresh(scout)
                await test_session.refresh(soldier)

                match = Match(log_id=88888, map="cp_gullywash", tournament_id=7)
                test_session.add(match)
                await test_session.commit()
                await test_session.refresh(match)

                # Scout has lower DPM but better KAD than Soldier.
                scout_stat = MatchStat(
                    match_id=match.id, # type: ignore[arg-type]
                    player_id=scout.id, # type: ignore[arg-type]
                    class_id=0,
                    team="Red",
                    playtime=900,
                    kills=24,
                    deaths=8,
                    dpm=260.0,
                    primary_accuracy=40.0,
                    damage_dealt=3900,
                    damage_received=2500,
                    heals_received=2000,
                    headshots=0,
                    backstabs=0,
                    airshots=0,
                    captures=2,
                )
                soldier_stat = MatchStat(
                    match_id=match.id, # type: ignore[arg-type]
                    player_id=soldier.id, # type: ignore[arg-type]
                    class_id=0,
                    team="Blue",
                    playtime=900,
                    kills=20,
                    deaths=10,
                    dpm=320.0,
                    primary_accuracy=35.0,
                    damage_dealt=4800,
                    damage_received=2600,
                    heals_received=2200,
                    headshots=0,
                    backstabs=0,
                    airshots=5,
                    captures=1,
                )
                test_session.add(scout_stat)
                test_session.add(soldier_stat)
                await test_session.commit()

        asyncio.run(seed_data())

        response = test_client.get("/tournaments/7/leaderboard?class_name=scout&sort_by=kad&sort_order=desc")
        assert response.status_code == 200

        payload = response.json()
        assert len(payload) == 2
        assert payload[0]["steamid"] == "steam_scout"
        assert payload[0]["avg_kad"] == 3.0
        assert payload[1]["steamid"] == "steam_soldier"
        assert payload[1]["avg_kad"] == 2.0
    finally:
        main.app.dependency_overrides.clear()


def test_leaderboard_supports_class_filter() -> None:
    test_client, session_factory = build_test_client_with_db()
    try:
        async def seed_data() -> None:
            async with session_factory() as test_session:
                tournament = Tournament(id=8, name="RGL")
                test_session.add(tournament)

                medic = Player(steamid="steam_medic", last_known_name="Medic")
                scout = Player(steamid="steam_scout2", last_known_name="Scout2")
                test_session.add(medic)
                test_session.add(scout)
                await test_session.commit()
                await test_session.refresh(medic)
                await test_session.refresh(scout)

                match = Match(log_id=99999, map="koth_product", tournament_id=8)
                test_session.add(match)
                await test_session.commit()
                await test_session.refresh(match)

                medic_stat = MatchStat(
                    match_id=match.id, # type: ignore[arg-type]
                    player_id=medic.id, # type: ignore[arg-type]
                    class_id=6,
                    team="Red",
                    playtime=1200,
                    kills=5,
                    deaths=4,
                    dpm=150.0,
                    primary_accuracy=30.0,
                    damage_dealt=3000,
                    damage_received=2800,
                    heals_received=9000,
                    headshots=0,
                    backstabs=0,
                    airshots=0,
                    captures=1,
                )
                scout_stat = MatchStat(
                    match_id=match.id, # type: ignore[arg-type]
                    player_id=scout.id, # type: ignore[arg-type]
                    class_id=0,
                    team="Blue",
                    playtime=1200,
                    kills=18,
                    deaths=8,
                    dpm=280.0,
                    primary_accuracy=45.0,
                    damage_dealt=5600,
                    damage_received=3500,
                    heals_received=4500,
                    headshots=0,
                    backstabs=0,
                    airshots=0,
                    captures=3,
                )
                test_session.add(medic_stat)
                test_session.add(scout_stat)
                await test_session.commit()

        asyncio.run(seed_data())

        response = test_client.get("/tournaments/8/leaderboard?class_name=medic")
        assert response.status_code == 200

        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["class"] == "Medic"
        assert payload[0]["steamid"] == "steam_medic"
    finally:
        main.app.dependency_overrides.clear()


def test_player_summary_includes_average_rating() -> None:
    test_client, session_factory = build_test_client_with_db()
    try:
        async def seed_data() -> None:
            async with session_factory() as test_session:
                tournament = Tournament(id=11, name="RGL")
                test_session.add(tournament)

                player = Player(steamid="steam_rating", last_known_name="Rated Player")
                test_session.add(player)
                await test_session.commit()
                await test_session.refresh(player)

                match_1 = Match(log_id=30001, map="cp_snakewater", tournament_id=11)
                match_2 = Match(log_id=30002, map="cp_process", tournament_id=11)
                test_session.add(match_1)
                test_session.add(match_2)
                await test_session.commit()
                await test_session.refresh(match_1)
                await test_session.refresh(match_2)

                stat_1 = MatchStat(
                    match_id=match_1.id, # type: ignore[arg-type]
                    player_id=player.id, # type: ignore[arg-type]
                    class_id=0,
                    team="Red",
                    playtime=900,
                    kills=22,
                    deaths=10,
                    dpm=280.0,
                    primary_accuracy=40.0,
                    damage_dealt=5100,
                    damage_received=3700,
                    heals_received=3200,
                    headshots=0,
                    backstabs=0,
                    airshots=0,
                    captures=2,
                )
                stat_2 = MatchStat(
                    match_id=match_2.id, # type: ignore[arg-type]
                    player_id=player.id, # type: ignore[arg-type]
                    class_id=0,
                    team="Blue",
                    playtime=960,
                    kills=19,
                    deaths=9,
                    dpm=265.0,
                    primary_accuracy=38.0,
                    damage_dealt=4850,
                    damage_received=3600,
                    heals_received=3000,
                    headshots=0,
                    backstabs=0,
                    airshots=0,
                    captures=1,
                )
                test_session.add(stat_1)
                test_session.add(stat_2)
                await test_session.commit()

        asyncio.run(seed_data())

        response = test_client.get("/players/steam_rating/summary")
        assert response.status_code == 200

        payload = response.json()
        assert "avg_rating" in payload["aggregate_stats"]
        assert isinstance(payload["aggregate_stats"]["avg_rating"], float)
        assert payload["aggregate_stats"]["avg_rating"] > 0.0
    finally:
        main.app.dependency_overrides.clear()


def test_player_summary_aggregates_multi_class_rows_into_single_match_entry() -> None:
    test_client, session_factory = build_test_client_with_db()
    try:
        async def seed_data() -> None:
            async with session_factory() as test_session:
                tournament = Tournament(id=21, name="ETF2L")
                test_session.add(tournament)

                player = Player(steamid="steam_multiclass", last_known_name="Flex")
                test_session.add(player)
                await test_session.commit()
                await test_session.refresh(player)

                match = Match(log_id=41001, map="cp_sunshine", tournament_id=21)
                test_session.add(match)
                await test_session.commit()
                await test_session.refresh(match)

                # One match with two class rows should still become one match-level entry.
                scout_row = MatchStat(
                    match_id=match.id, # type: ignore[arg-type]
                    player_id=player.id, # type: ignore[arg-type]
                    class_id=0,
                    team="Red",
                    playtime=600,
                    kills=12,
                    deaths=5,
                    dpm=300.0,
                    primary_accuracy=42.0,
                    damage_dealt=3000,
                    damage_received=2200,
                    heals_received=1600,
                    headshots=0,
                    backstabs=0,
                    airshots=0,
                    captures=1,
                )
                soldier_row = MatchStat(
                    match_id=match.id, # type: ignore[arg-type]
                    player_id=player.id, # type: ignore[arg-type]
                    class_id=1,
                    team="Red",
                    playtime=600,
                    kills=8,
                    deaths=4,
                    dpm=180.0,
                    primary_accuracy=30.0,
                    damage_dealt=1800,
                    damage_received=1800,
                    heals_received=1200,
                    headshots=0,
                    backstabs=0,
                    airshots=2,
                    captures=0,
                )
                test_session.add(scout_row)
                test_session.add(soldier_row)
                await test_session.commit()

        asyncio.run(seed_data())

        response = test_client.get("/players/steam_multiclass/summary")
        assert response.status_code == 200

        payload = response.json()
        assert payload["aggregate_stats"]["matches_played"] == 1
        assert len(payload["matches"]) == 1
        assert payload["matches"][0]["kills"] == 20
        assert payload["matches"][0]["deaths"] == 9
        assert payload["matches"][0]["dpm"] == 240.0
        assert "class_name" not in payload["matches"][0]
    finally:
        main.app.dependency_overrides.clear()


def test_player_class_aggregate_endpoint_returns_class_specific_stats() -> None:
    test_client, session_factory = build_test_client_with_db()
    try:
        async def seed_data() -> None:
            async with session_factory() as test_session:
                tournament = Tournament(id=22, name="RGL")
                test_session.add(tournament)

                player = Player(steamid="steam_scoutagg", last_known_name="ScoutMain")
                test_session.add(player)
                await test_session.commit()
                await test_session.refresh(player)

                match_1 = Match(log_id=42001, map="cp_badlands", tournament_id=22)
                match_2 = Match(log_id=42002, map="cp_reckoner", tournament_id=22)
                test_session.add(match_1)
                test_session.add(match_2)
                await test_session.commit()
                await test_session.refresh(match_1)
                await test_session.refresh(match_2)

                stat_1 = MatchStat(
                    match_id=match_1.id, # type: ignore[arg-type]
                    player_id=player.id, # type: ignore[arg-type]
                    class_id=0,
                    team="Blue",
                    playtime=900,
                    kills=18,
                    deaths=9,
                    dpm=260.0,
                    primary_accuracy=41.0,
                    damage_dealt=3900,
                    damage_received=2800,
                    heals_received=2400,
                    headshots=0,
                    backstabs=0,
                    airshots=0,
                    captures=2,
                )
                stat_2 = MatchStat(
                    match_id=match_2.id, # type: ignore[arg-type]
                    player_id=player.id, # type: ignore[arg-type]
                    class_id=0,
                    team="Blue",
                    playtime=960,
                    kills=20,
                    deaths=10,
                    dpm=275.0,
                    primary_accuracy=43.0,
                    damage_dealt=4400,
                    damage_received=3000,
                    heals_received=2600,
                    headshots=0,
                    backstabs=0,
                    airshots=0,
                    captures=1,
                )
                test_session.add(stat_1)
                test_session.add(stat_2)
                await test_session.commit()

        asyncio.run(seed_data())

        response = test_client.get("/player/steam_scoutagg/0")
        assert response.status_code == 200

        payload = response.json()
        assert payload["steamid"] == "steam_scoutagg"
        assert payload["class_id"] == 0
        assert payload["class_name"] == "Scout"
        assert payload["aggregate_stats"]["matches_played"] == 2
        assert payload["aggregate_stats"]["total_kills"] == 38
        assert payload["aggregate_stats"]["avg_rating"] > 0.0
    finally:
        main.app.dependency_overrides.clear()
