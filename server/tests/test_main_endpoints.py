from fastapi.testclient import TestClient
from fastapi import BackgroundTasks
import asyncio
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.engine import Engine

import src.main as main
from src.models import Match, MatchStat, Player, Class, Tournament, seed_classes


client = TestClient(main.app)


def build_test_client_with_db() -> tuple[TestClient, Engine]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        seed_classes(session)

    def get_test_session():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[main.get_session] = get_test_session
    return TestClient(main.app), engine


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


def test_health_endpoint_returns_ok() -> None:
    test_client, engine = build_test_client_with_db()
    try:
        response = test_client.get("/health/")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    finally:
        main.app.dependency_overrides.clear()


def test_log_stats_endpoint_returns_match_stats() -> None:
    test_client, engine = build_test_client_with_db()
    try:
        with Session(engine) as test_session:
            player = Player(steamid="steam_abc", last_known_name="MedicMain")
            test_session.add(player)
            test_session.commit()
            test_session.refresh(player)

            match = Match(log_id=24680, map="cp_process", tournament_id=1)
            test_session.add(match)
            test_session.commit()
            test_session.refresh(match)

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
            test_session.commit()

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
    test_client, engine = build_test_client_with_db()
    try:
        with Session(engine) as test_session:
            tournament = Tournament(id=7, name="Invite")
            test_session.add(tournament)

            scout = Player(steamid="steam_scout", last_known_name="Scout")
            soldier = Player(steamid="steam_soldier", last_known_name="Soldier")
            test_session.add(scout)
            test_session.add(soldier)
            test_session.commit()
            test_session.refresh(scout)
            test_session.refresh(soldier)

            match = Match(log_id=88888, map="cp_gullywash", tournament_id=7)
            test_session.add(match)
            test_session.commit()
            test_session.refresh(match)

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
                class_id=1,
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
            test_session.commit()

        response = test_client.get("/tournaments/7/leaderboard?sort_by=kad&sort_order=desc")
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
    test_client, engine = build_test_client_with_db()
    try:
        with Session(engine) as test_session:
            tournament = Tournament(id=8, name="RGL")
            test_session.add(tournament)

            medic = Player(steamid="steam_medic", last_known_name="Medic")
            scout = Player(steamid="steam_scout2", last_known_name="Scout2")
            test_session.add(medic)
            test_session.add(scout)
            test_session.commit()
            test_session.refresh(medic)
            test_session.refresh(scout)

            match = Match(log_id=99999, map="koth_product", tournament_id=8)
            test_session.add(match)
            test_session.commit()
            test_session.refresh(match)

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
            test_session.commit()

        response = test_client.get("/tournaments/8/leaderboard?class_name=medic")
        assert response.status_code == 200

        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["class"] == "Medic"
        assert payload[0]["steamid"] == "steam_medic"
    finally:
        main.app.dependency_overrides.clear()
