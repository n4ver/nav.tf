"""Unit tests for JWT configuration helpers."""

from __future__ import annotations

from cqrs.shared.auth import UserRole, create_access_token, decode_access_token
from cqrs.shared.auth.jwt import DEFAULT_EXPIRE_MINUTES, _expire_minutes, _secret


def test_secret_uses_dev_fallback_when_unset(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    assert "dev-insecure" in _secret()


def test_expire_minutes_invalid_env_defaults(monkeypatch):
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "not-int")
    assert _expire_minutes() == DEFAULT_EXPIRE_MINUTES


def test_expire_minutes_custom_value(monkeypatch):
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "120")
    assert _expire_minutes() == 120


def test_create_access_token_includes_extra_claims():
    token = create_access_token(
        steam_id="76561198000000001",
        role=UserRole.ADMIN,
        display_name="Admin",
        extra_claims={"scope": "test"},
    )
    claims = decode_access_token(token)
    assert claims["scope"] == "test"
    assert claims["role"] == "ADMIN"
