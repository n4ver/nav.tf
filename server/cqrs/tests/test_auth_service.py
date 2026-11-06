"""Unit tests for AuthService and auth helpers."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from cqrs.command_service.app.auth_service import (
    AuthService,
    _bootstrap_admin_ids,
    _login_code_ttl_seconds,
)
from cqrs.command_service.app.db import SessionLocal
from cqrs.shared.auth import UserRole


class FakeSteamClient:
    async def get_player_summaries(self, steam_ids: list[str]) -> dict:
        return {
            sid: {
                "personaname": f"Persona-{sid[-4:]}",
                "avatarfull": "https://example.com/avatar.jpg",
            }
            for sid in steam_ids
        }


def _random_steam_id64() -> str:
    return str(76561197960265728 + uuid.uuid4().int % 10_000_000)


def test_bootstrap_admin_ids_empty_without_env(monkeypatch):
    monkeypatch.delenv("BOOTSTRAP_ADMIN_STEAM_IDS", raising=False)
    assert _bootstrap_admin_ids() == set()


def test_bootstrap_admin_ids_parses_csv(monkeypatch):
    steam_id = _random_steam_id64()
    monkeypatch.setenv("BOOTSTRAP_ADMIN_STEAM_IDS", f"STEAM_1:1:4242, {steam_id}")
    ids = _bootstrap_admin_ids()
    assert "STEAM_1:1:4242" in ids
    assert steam_id in ids


def test_login_code_ttl_defaults(monkeypatch):
    monkeypatch.delenv("AUTH_CODE_TTL_SECONDS", raising=False)
    assert _login_code_ttl_seconds() == 60


def test_login_code_ttl_invalid_env_falls_back(monkeypatch):
    monkeypatch.setenv("AUTH_CODE_TTL_SECONDS", "not-a-number")
    assert _login_code_ttl_seconds() == 60


def test_login_code_ttl_respects_minimum(monkeypatch):
    monkeypatch.setenv("AUTH_CODE_TTL_SECONDS", "5")
    assert _login_code_ttl_seconds() == 15


def test_auth_service_upsert_creates_player():
    steam_id = _random_steam_id64()

    async def run() -> None:
        async with SessionLocal() as session:
            auth = AuthService(session, steam_client=FakeSteamClient())
            user = await auth.upsert_steam_user(steam_id)
            assert user.steam_id == steam_id
            assert user.role == UserRole.PLAYER
            assert user.display_name.startswith("Persona-")
            assert user.avatar_url == "https://example.com/avatar.jpg"

            token = auth.issue_token(user)
            assert token
            public = auth.user_public_dict(user)
            assert public["steam_id"] == steam_id
            assert public["role"] == "PLAYER"

    asyncio.run(run())


def test_auth_service_upsert_promotes_bootstrap_admin(monkeypatch):
    steam_id = _random_steam_id64()
    monkeypatch.setenv("BOOTSTRAP_ADMIN_STEAM_IDS", steam_id)

    async def run() -> None:
        async with SessionLocal() as session:
            auth = AuthService(session, steam_client=FakeSteamClient())
            user = await auth.upsert_steam_user(steam_id)
            assert user.role == UserRole.ADMIN

    asyncio.run(run())


def test_auth_service_upsert_promotes_existing_user_to_admin(monkeypatch):
    steam_id = _random_steam_id64()

    async def run() -> None:
        async with SessionLocal() as session:
            auth = AuthService(session, steam_client=FakeSteamClient())
            created = await auth.upsert_steam_user(steam_id)
            assert created.role == UserRole.PLAYER

            monkeypatch.setenv("BOOTSTRAP_ADMIN_STEAM_IDS", steam_id)
            promoted = await auth.upsert_steam_user(steam_id)
            assert promoted.role == UserRole.ADMIN

    asyncio.run(run())


def test_bootstrap_admin_ids_skips_empty_csv_parts(monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_ADMIN_STEAM_IDS", " , , ")
    assert _bootstrap_admin_ids() == set()


def test_auth_service_upsert_updates_existing_user():
    steam_id = _random_steam_id64()

    async def run() -> None:
        async with SessionLocal() as session:
            auth = AuthService(session, steam_client=FakeSteamClient())
            first = await auth.upsert_steam_user(steam_id)
            second = await auth.upsert_steam_user(steam_id)
            assert second.steam_id == first.steam_id
            assert second.display_name.startswith("Persona-")
            assert second.last_login_at >= first.last_login_at

    asyncio.run(run())


def test_exchange_login_code_rejects_empty_string():
    async def run() -> None:
        async with SessionLocal() as session:
            auth = AuthService(session)
            with pytest.raises(ValueError, match="required"):
                await auth.exchange_login_code("  ")

    asyncio.run(run())


def test_create_and_exchange_login_code():
    steam_id = _random_steam_id64()

    async def run() -> None:
        async with SessionLocal() as session:
            auth = AuthService(session, steam_client=FakeSteamClient())
            user = await auth.upsert_steam_user(steam_id)
            token = auth.issue_token(user)
            code = await auth.create_login_code(token)
            assert len(code) > 20
            assert await auth.exchange_login_code(code) == token

    asyncio.run(run())
