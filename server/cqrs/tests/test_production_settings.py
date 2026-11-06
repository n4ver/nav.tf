"""Production startup guards (APP_ENV=production)."""

from __future__ import annotations

import pytest

from cqrs.shared import settings
from cqrs.shared.cors import _allowed_origins
from cqrs.shared.settings import (
    InsecureConfigurationError,
    enforce_production_settings,
    fastapi_docs_kwargs,
    production_problems,
)

STRONG = "a" * 64

GOOD_ENV = {
    "APP_ENV": "production",
    "JWT_SECRET": STRONG,
    "SEED_SERVICE_TOKEN": "b" * 64,
    "FRONTEND_URL": "https://nav.example",
    "STEAM_OPENID_REALM": "https://nav.example",
    "STEAM_OPENID_RETURN_TO": "https://nav.example/api/auth/steam/callback",
    "CQRS_COMMAND_DATABASE_URL": "postgresql+asyncpg://navtf:s3cret@db:5432/cqrs_command",
    "CQRS_QUERY_DATABASE_URL": "postgresql+asyncpg://navtf:s3cret@db:5432/cqrs_query",
    "RABBITMQ_URL": "amqp://navtf:s3cret@rabbitmq:5672/",
    "CQRS_BROKER_MODE": "",
}


@pytest.fixture
def prod_env(monkeypatch):
    for key, value in GOOD_ENV.items():
        monkeypatch.setenv(key, value)
    return monkeypatch


def test_good_production_config_passes(prod_env):
    assert production_problems("command") == []
    assert production_problems("query") == []
    enforce_production_settings("command")
    enforce_production_settings("query")


def test_non_production_is_never_enforced(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("JWT_SECRET", "")
    enforce_production_settings("command")  # dev defaults are fine outside prod


@pytest.mark.parametrize(
    ("key", "value", "fragment"),
    [
        ("JWT_SECRET", "", "JWT_SECRET must be set"),
        ("JWT_SECRET", settings.DEV_JWT_SECRET, "JWT_SECRET must be set"),
        ("JWT_SECRET", "short", "at least 32"),
        ("SEED_SERVICE_TOKEN", settings.DEV_SEED_SERVICE_TOKEN, "development default"),
        ("SEED_SERVICE_TOKEN", "short", "empty or at least 32"),
        ("STEAM_OPENID_REALM", "http://nav.example", "STEAM_OPENID_REALM"),
        ("STEAM_OPENID_RETURN_TO", "", "STEAM_OPENID_RETURN_TO"),
        (
            "CQRS_COMMAND_DATABASE_URL",
            "postgresql+asyncpg://user:password@db:5432/cqrs_command",
            "development credentials",
        ),
        ("CQRS_COMMAND_DATABASE_URL", "", "CQRS_COMMAND_DATABASE_URL must be set"),
        ("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/", "RABBITMQ_URL"),
        ("FRONTEND_URL", "http://nav.example", "FRONTEND_URL"),
        ("CQRS_BROKER_MODE", "memory", "CQRS_BROKER_MODE"),
    ],
)
def test_command_side_rejects_insecure_values(prod_env, key, value, fragment):
    prod_env.setenv(key, value)
    problems = production_problems("command")
    assert any(fragment in problem for problem in problems), problems
    with pytest.raises(InsecureConfigurationError, match="command service"):
        enforce_production_settings("command")


def test_empty_seed_token_is_allowed(prod_env):
    prod_env.setenv("SEED_SERVICE_TOKEN", "")
    assert production_problems("command") == []


def test_query_side_checks_only_what_it_uses(prod_env):
    # The query service never signs tokens or talks to Steam OpenID.
    prod_env.setenv("JWT_SECRET", "")
    prod_env.setenv("STEAM_OPENID_REALM", "")
    assert production_problems("query") == []

    prod_env.setenv(
        "CQRS_QUERY_DATABASE_URL",
        "postgresql+asyncpg://user:password@db:5432/cqrs_query",
    )
    assert production_problems("query") == [
        "CQRS_QUERY_DATABASE_URL uses development credentials"
    ]


def test_api_docs_hidden_in_production_unless_enabled(prod_env):
    assert fastapi_docs_kwargs() == {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }
    prod_env.setenv("API_DOCS_ENABLED", "true")
    assert fastapi_docs_kwargs() == {}


def test_api_docs_enabled_in_development(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("API_DOCS_ENABLED", raising=False)
    assert fastapi_docs_kwargs() == {}
    monkeypatch.setenv("API_DOCS_ENABLED", "false")
    assert fastapi_docs_kwargs()["openapi_url"] is None


def test_cors_allows_only_frontend_origin_in_production(prod_env):
    prod_env.delenv("CORS_ORIGINS", raising=False)
    assert _allowed_origins() == ["https://nav.example"]


def test_cors_origins_override_still_applies_in_production(prod_env):
    prod_env.setenv("CORS_ORIGINS", "https://a.example,https://b.example")
    assert _allowed_origins() == ["https://a.example", "https://b.example"]
