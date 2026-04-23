import asyncio

from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from models import Class, Player, get_class_id_from_name, get_or_create_player, seed_classes # type: ignore


def build_test_session() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def initialize_database() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)

    asyncio.run(initialize_database())
    return session_factory


def test_get_class_id_from_name_known_and_unknown() -> None:
    assert get_class_id_from_name("scout") == 0
    assert get_class_id_from_name("medic") == 6
    assert get_class_id_from_name("heavyweapons") == 4
    assert get_class_id_from_name("unknown_class") == 0


def test_get_or_create_player_returns_same_id_for_existing_player() -> None:
    session_factory = build_test_session()

    async def run_test() -> None:
        async with session_factory() as session:
            first_id = await get_or_create_player(session, "steam_123", "Player One")
            second_id = await get_or_create_player(session, "steam_123", "Player One")

            assert first_id == second_id

            players = (await session.execute(select(Player).where(Player.steamid == "steam_123"))).scalars().all()
            assert len(players) == 1

    asyncio.run(run_test())


def test_seed_classes_is_idempotent() -> None:
    session_factory = build_test_session()

    async def run_test() -> None:
        async with session_factory() as session:
            await seed_classes(session)
            await seed_classes(session)

            classes = (await session.execute(select(Class))).scalars().all()
            assert len(classes) == 9
            assert {item.name for item in classes} == {
                "Scout",
                "Soldier",
                "Pyro",
                "Demoman",
                "Heavy",
                "Engineer",
                "Medic",
                "Sniper",
                "Spy",
            }

    asyncio.run(run_test())
