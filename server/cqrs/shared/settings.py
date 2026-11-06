"""Runtime environment checks shared by the command and query services.

Development defaults (a dev JWT secret, ``user:password`` database URLs, the
``guest`` RabbitMQ account, localhost CORS) keep local setup friction-free. In
production (``APP_ENV=production``) the services refuse to start with any of
them, so a missing secret fails loudly at deploy time instead of silently
weakening auth.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Literal

DEV_JWT_SECRET = "dev-insecure-jwt-secret-change-me"
DEV_SEED_SERVICE_TOKEN = "dev-seed-service-token"
MIN_SECRET_LENGTH = 32
_DEV_CREDENTIAL_MARKERS = ("user:password@", "guest:guest@")

Side = Literal["command", "query"]


class InsecureConfigurationError(RuntimeError):
    """Raised at startup when production is configured with development values."""


def is_production() -> bool:
    return os.getenv("APP_ENV", "").strip().lower() == "production"


def api_docs_enabled() -> bool:
    """Interactive /docs and /openapi.json: on in dev, opt-in in production."""
    raw = os.getenv("API_DOCS_ENABLED", "").strip().lower()
    if raw:
        return raw in {"1", "true", "yes", "on"}
    return not is_production()


def fastapi_docs_kwargs() -> dict[str, str | None]:
    if api_docs_enabled():
        return {}
    return {"docs_url": None, "redoc_url": None, "openapi_url": None}


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _require_https(name: str, problems: list[str]) -> None:
    value = _env(name)
    if not value.lower().startswith("https://"):
        problems.append(f"{name} must be an https:// URL (got {value or 'unset'!r})")


def _reject_dev_credentials(names: Iterable[str], problems: list[str]) -> None:
    for name in names:
        value = _env(name)
        if not value:
            problems.append(f"{name} must be set")
        elif any(marker in value for marker in _DEV_CREDENTIAL_MARKERS):
            problems.append(f"{name} uses development credentials")


def production_problems(side: Side) -> list[str]:
    """Return every reason the current environment is unsafe for production."""
    problems: list[str] = []

    jwt_secret = _env("JWT_SECRET")
    if side == "command":
        # Only the command side signs and verifies tokens.
        if not jwt_secret or jwt_secret == DEV_JWT_SECRET:
            problems.append("JWT_SECRET must be set to a non-default value")
        elif len(jwt_secret) < MIN_SECRET_LENGTH:
            problems.append(
                f"JWT_SECRET must be at least {MIN_SECRET_LENGTH} characters"
            )
        seed_token = _env("SEED_SERVICE_TOKEN")
        if seed_token == DEV_SEED_SERVICE_TOKEN:
            problems.append("SEED_SERVICE_TOKEN must not be the development default")
        elif seed_token and len(seed_token) < MIN_SECRET_LENGTH:
            problems.append(
                f"SEED_SERVICE_TOKEN must be empty or at least "
                f"{MIN_SECRET_LENGTH} characters"
            )
        _require_https("STEAM_OPENID_REALM", problems)
        _require_https("STEAM_OPENID_RETURN_TO", problems)
        _reject_dev_credentials(["CQRS_COMMAND_DATABASE_URL"], problems)
    else:
        _reject_dev_credentials(["CQRS_QUERY_DATABASE_URL"], problems)

    _require_https("FRONTEND_URL", problems)
    _reject_dev_credentials(["RABBITMQ_URL"], problems)
    if _env("CQRS_BROKER_MODE").lower() == "memory":
        problems.append("CQRS_BROKER_MODE=memory is not allowed in production")
    return problems


def enforce_production_settings(side: Side) -> None:
    """Fail service startup when production is configured with dev values."""
    if not is_production():
        return
    problems = production_problems(side)
    if problems:
        raise InsecureConfigurationError(
            f"Refusing to start the {side} service with APP_ENV=production:\n- "
            + "\n- ".join(problems)
        )
