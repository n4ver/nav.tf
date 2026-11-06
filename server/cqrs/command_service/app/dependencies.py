"""Command-side FastAPI dependencies (sessions + JWT RBAC)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ...shared.auth import (
    UserRole,
    decode_access_token,
    is_seed_service_token,
    seed_actor_steam_id,
)
from ...shared.steam import canonical_steam_id
from .db import get_write_session
from .models import User

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    steam_id: str
    role: UserRole
    display_name: str | None = None
    avatar_url: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_write_session)],
) -> AuthenticatedUser:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    if is_seed_service_token(token):
        return AuthenticatedUser(
            steam_id=seed_actor_steam_id(),
            role=UserRole.ADMIN,
            display_name="Seed Service",
        )

    try:
        claims = decode_access_token(token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    steam_id = canonical_steam_id(
        str(claims.get("steam_id") or claims.get("sub") or "").strip()
    )
    if not steam_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing steam_id"
        )

    role_raw = str(claims.get("role") or UserRole.PLAYER.value).upper()
    try:
        role = UserRole(role_raw)
    except ValueError:
        role = UserRole.PLAYER

    # Prefer live role from write DB so demotions take effect without waiting for token expiry.
    db_user = (
        (await session.execute(select(User).where(User.steam_id == steam_id)))
        .scalars()
        .first()
    )
    if db_user is not None:
        role = (
            db_user.role
            if isinstance(db_user.role, UserRole)
            else UserRole(str(db_user.role))
        )
        return AuthenticatedUser(
            steam_id=db_user.steam_id,
            role=role,
            display_name=db_user.display_name,
            avatar_url=db_user.avatar_url,
        )

    return AuthenticatedUser(
        steam_id=steam_id,
        role=role,
        display_name=claims.get("display_name"),
    )


async def get_current_admin_user(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return user


__all__ = [
    "AuthenticatedUser",
    "get_current_admin_user",
    "get_current_user",
    "get_write_session",
]
