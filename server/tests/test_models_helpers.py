from sqlmodel import SQLModel, Session, create_engine, select

from models import Class, Player, get_class_id_from_name, get_or_create_player, seed_classes


def build_test_session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_get_class_id_from_name_known_and_unknown() -> None:
    assert get_class_id_from_name("scout") == 0
    assert get_class_id_from_name("medic") == 6
    assert get_class_id_from_name("heavyweapons") == 4
    assert get_class_id_from_name("unknown_class") == 0


def test_get_or_create_player_returns_same_id_for_existing_player() -> None:
    with build_test_session() as session:
        first_id = get_or_create_player(session, "steam_123", "Player One")
        second_id = get_or_create_player(session, "steam_123", "Player One")

        assert first_id == second_id

        players = session.exec(select(Player).where(Player.steamid == "steam_123")).all()
        assert len(players) == 1


def test_seed_classes_is_idempotent() -> None:
    with build_test_session() as session:
        seed_classes(session)
        seed_classes(session)

        classes = session.exec(select(Class)).all()
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
