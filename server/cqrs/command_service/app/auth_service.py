"""Auth domain service: Steam login upsert + JWT issuance."""

from __future__ import annotations

import os
import secrets
from datetime import timedelta
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ...shared.auth import UserRole, create_access_token
from ...shared.steam import SteamWebApiClient, to_steam_id64
from ...shared.timeutils import utcnow
from .models import AuthLoginCode, User


def _bootstrap_admin_ids() -> set[str]:
    raw = os.getenv("BOOTSTRAP_ADMIN_STEAM_IDS", "").strip()
    if not raw:
        return set()
    ids: set[str] = set()
    for part in raw.split(","):
        value = part.strip()
        if not value:
            continue
        ids.add(value)
        sid64 = to_steam_id64(value)
        if sid64:
            ids.add(sid64)
    return ids


def _login_code_ttl_seconds() -> int:
    raw = os.getenv("AUTH_CODE_TTL_SECONDS", "").strip()
    if not raw:
        return 60
    try:
        return max(15, int(raw))
    except ValueError:
        return 60


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        steam_client: SteamWebApiClient | None = None,
    ) -> None:
        self.session = session
        self.steam_client = steam_client or SteamWebApiClient()

    async def upsert_steam_user(self, steam_id: str) -> User:
        sid64 = to_steam_id64(steam_id) or steam_id
        existing = (
            await self.session.execute(select(User).where(User.steam_id == sid64))
        ).scalars().first()

        display_name = sid64
        avatar_url: str | None = None
        summaries = await self.steam_client.get_player_summaries([sid64])
        summary = summaries.get(sid64) or {}
        if summary:
            display_name = str(summary.get("personaname") or display_name)
            avatar_url = summary.get("avatarfull") or summary.get("avatarmedium") or summary.get("avatar")

        now = utcnow()
        bootstrap_admins = _bootstrap_admin_ids()
        if existing is None:
            role = UserRole.ADMIN if sid64 in bootstrap_admins else UserRole.PLAYER
            user = User(
                steam_id=sid64,
                display_name=display_name,
                avatar_url=avatar_url,
                role=role,
                created_at=now,
                updated_at=now,
                last_login_at=now,
            )
            self.session.add(user)
        else:
            user = existing
            user.display_name = display_name or user.display_name
            if avatar_url:
                user.avatar_url = avatar_url
            if sid64 in bootstrap_admins and user.role != UserRole.ADMIN:
                user.role = UserRole.ADMIN
            user.updated_at = now
            user.last_login_at = now

        await self.session.commit()
        await self.session.refresh(user)
        return user

    def issue_token(self, user: User) -> str:
        return create_access_token(
            steam_id=user.steam_id,
            role=user.role,
            display_name=user.display_name,
        )

    async def create_login_code(self, token: str) -> str:
        code = secrets.token_urlsafe(32)
        now = utcnow()
        self.session.add(
            AuthLoginCode(
                code=code,
                token=token,
                created_at=now,
                expires_at=now + timedelta(seconds=_login_code_ttl_seconds()),
            )
        )
        await self.session.commit()
        return code

    async def exchange_login_code(self, code: str) -> str:
        key = str(code or "").strip()
        if not key:
            raise ValueError("Authorization code is required")

        now = utcnow()
        result = await self.session.execute(
            update(AuthLoginCode)
            .where(AuthLoginCode.code == key)
            .where(AuthLoginCode.used_at.is_(None))
            .where(AuthLoginCode.expires_at >= now)
            .values(used_at=now)
            .returning(AuthLoginCode.token)
        )
        token = result.scalar_one_or_none()
        if token is None:
            raise ValueError("Invalid or expired authorization code")

        await self.session.commit()
        return str(token)

    def user_public_dict(self, user: User) -> dict[str, Any]:
        return {
            "steam_id": user.steam_id,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
            "role": user.role.value if isinstance(user.role, UserRole) else str(user.role),
        }
