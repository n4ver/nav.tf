"""JWT creation and verification for Steam-authenticated sessions."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from .roles import UserRole

ALGORITHM = "HS256"
DEFAULT_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days


def _secret() -> str:
    secret = os.getenv("JWT_SECRET", "").strip()
    if not secret:
        # Dev fallback — production must set JWT_SECRET.
        secret = "dev-insecure-jwt-secret-change-me"
    return secret


def _expire_minutes() -> int:
    raw = os.getenv("JWT_EXPIRE_MINUTES", "").strip()
    if not raw:
        return DEFAULT_EXPIRE_MINUTES
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_EXPIRE_MINUTES


def create_access_token(
    *,
    steam_id: str,
    role: UserRole | str,
    display_name: str | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    role_value = role.value if isinstance(role, UserRole) else str(role)
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": steam_id,
        "steam_id": steam_id,
        "role": role_value,
        "display_name": display_name,
        "iat": now,
        "exp": now + timedelta(minutes=_expire_minutes()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, _secret(), algorithms=[ALGORITHM])
