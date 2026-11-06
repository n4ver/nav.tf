"""Unit tests for database URL helpers."""

from __future__ import annotations

from cqrs.shared.paths import normalize_async_database_url, postgres_url


def test_postgres_url_uses_env_overrides(monkeypatch):
    monkeypatch.setenv("CQRS_POSTGRES_HOST", "db.example")
    monkeypatch.setenv("CQRS_POSTGRES_PORT", "5433")
    monkeypatch.setenv("CQRS_POSTGRES_USER", "app")
    monkeypatch.setenv("CQRS_POSTGRES_PASSWORD", "secret")
    url = postgres_url("cqrs_command")
    assert url == "postgresql+asyncpg://app:secret@db.example:5433/cqrs_command"


def test_normalize_async_database_url_upgrades_postgres_scheme():
    assert normalize_async_database_url("postgres://user:pass@localhost/db") == (
        "postgresql+asyncpg://user:pass@localhost/db"
    )
