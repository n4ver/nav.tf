"""CQRS integration test configuration (Postgres)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

SERVER_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER_ROOT))
sys.path.insert(0, str(SERVER_ROOT / "dev-setup"))

from postgres import (
    create_postgres_engine,
    dispose_engine,
    postgres_test_url,
    sync_truncate_database,
)

os.environ["CQRS_BROKER_MODE"] = "memory"
os.environ["JWT_SECRET"] = os.getenv("JWT_SECRET", "test-jwt-secret")
os.environ["CQRS_COMMAND_DATABASE_URL"] = os.getenv(
    "CQRS_COMMAND_TEST_DATABASE_URL",
    postgres_test_url("cqrs_command_test"),
)
os.environ["CQRS_QUERY_DATABASE_URL"] = os.getenv(
    "CQRS_QUERY_TEST_DATABASE_URL",
    postgres_test_url("cqrs_query_test"),
)

from cqrs.command_service.app.main import app as command_app
from cqrs.query_service.app.main import app as query_app
from cqrs.shared.auth import UserRole, create_access_token

ADMIN_STEAM_ID = "76561198000000001"
PLAYER_STEAM_ID = "76561198000000002"


def admin_auth_headers() -> dict[str, str]:
    token = create_access_token(
        steam_id=ADMIN_STEAM_ID,
        role=UserRole.ADMIN,
        display_name="Test Admin",
    )
    return {"Authorization": f"Bearer {token}"}


def player_auth_headers() -> dict[str, str]:
    token = create_access_token(
        steam_id=PLAYER_STEAM_ID,
        role=UserRole.PLAYER,
        display_name="Test Player",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session", autouse=True)
def postgres_available() -> None:
    for database in ("cqrs_command_test", "cqrs_query_test"):
        engine = create_postgres_engine(database)

        async def probe(engine=engine) -> None:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))

        try:
            asyncio.run(probe())
        except Exception:  # noqa: BLE001
            pytest.fail(
                f"Postgres test database {database} is unavailable. "
                "Start Docker Postgres: docker compose up -d db db-init"
            )
        finally:
            dispose_engine(engine)


@pytest.fixture
def client():
    from cqrs.command_service.app.db import engine as command_engine
    from cqrs.query_service.app.db import engine as query_engine

    sync_truncate_database("cqrs_command_test")
    sync_truncate_database("cqrs_query_test")
    dispose_engine(command_engine)
    dispose_engine(query_engine)

    with (
        TestClient(command_app) as command_client,
        TestClient(query_app) as query_client,
    ):
        # Default command mutations as admin so existing write-path tests stay green.
        _post = command_client.post
        _patch = command_client.patch

        def post_with_admin(url, **kwargs):
            headers = dict(kwargs.pop("headers", None) or {})
            if "Authorization" not in headers:
                headers.update(admin_auth_headers())
            return _post(url, headers=headers, **kwargs)

        def patch_with_admin(url, **kwargs):
            headers = dict(kwargs.pop("headers", None) or {})
            if "Authorization" not in headers:
                headers.update(admin_auth_headers())
            return _patch(url, headers=headers, **kwargs)

        command_client.post = post_with_admin  # type: ignore[method-assign]
        command_client.patch = patch_with_admin  # type: ignore[method-assign]
        yield {"command": command_client, "query": query_client}

    dispose_engine(command_engine)
    dispose_engine(query_engine)


@pytest.fixture
def admin_headers():
    return admin_auth_headers()


@pytest.fixture
def player_headers():
    return player_auth_headers()


@pytest.fixture
def raw_client():
    """Test clients without auto-injected admin auth on POST/PATCH."""
    from cqrs.command_service.app.db import engine as command_engine
    from cqrs.query_service.app.db import engine as query_engine

    sync_truncate_database("cqrs_command_test")
    sync_truncate_database("cqrs_query_test")
    dispose_engine(command_engine)
    dispose_engine(query_engine)

    with (
        TestClient(command_app) as command_client,
        TestClient(query_app) as query_client,
    ):
        yield {"command": command_client, "query": query_client}

    dispose_engine(command_engine)
    dispose_engine(query_engine)


@pytest.fixture
def clean_dbs():
    """Empty, migrated command and query databases without starting either app.

    Use this instead of ``client`` for tests that drive the outbox relay or the
    rating rebuild directly: the apps' background workers (outbox relay, rating
    rebuild) would otherwise race the test.
    """
    from cqrs.command_service.app.db import engine as command_engine
    from cqrs.command_service.app.db import init_write_db
    from cqrs.query_service.app.db import engine as query_engine
    from cqrs.query_service.app.db import init_read_db

    async def _init() -> None:
        await init_write_db()
        await init_read_db()

    asyncio.run(_init())
    sync_truncate_database("cqrs_command_test")
    sync_truncate_database("cqrs_query_test")
    dispose_engine(command_engine)
    dispose_engine(query_engine)
    yield
    dispose_engine(command_engine)
    dispose_engine(query_engine)
