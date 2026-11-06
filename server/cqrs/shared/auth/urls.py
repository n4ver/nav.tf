"""Resolve public HTTP URLs for Steam OpenID redirects."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from ..settings import is_production

if TYPE_CHECKING:
    from starlette.requests import Request

# Browser-facing path (Vite + Nginx rewrite this to /api/v1/auth on the command service).
PUBLIC_STEAM_CALLBACK_PATH = "/api/auth/steam/callback"


def _force_http_for_local_dev(url: str) -> str:
    """Browsers often upgrade localhost to HTTPS; Steam callback must stay on HTTP in dev.

    Never applied in production, where configured https:// URLs are used as-is.
    """
    if is_production():
        return url
    lowered = url.lower()
    if lowered.startswith(("https://localhost", "https://127.0.0.1")):
        return "http://" + url.split("://", 1)[1]
    return url


def resolve_public_base_url(request: Request) -> str | None:
    """Best-effort browser-visible origin (respects Vite/nginx X-Forwarded-* headers)."""
    forwarded_host = (request.headers.get("x-forwarded-host") or "").strip()
    if forwarded_host:
        host = forwarded_host.split(",", 1)[0].strip()
        proto = (
            (request.headers.get("x-forwarded-proto") or "http")
            .split(",", 1)[0]
            .strip()
        )
        return _force_http_for_local_dev(f"{proto}://{host}".rstrip("/"))

    host = (request.headers.get("host") or "").strip()
    if host:
        scheme = request.url.scheme or "http"
        return _force_http_for_local_dev(f"{scheme}://{host}".rstrip("/"))

    return None


def resolve_frontend_url(request: Request) -> str:
    configured = os.getenv("FRONTEND_URL", "").strip()
    if configured:
        return _force_http_for_local_dev(configured.rstrip("/"))

    derived = resolve_public_base_url(request)
    if derived:
        return derived

    return os.getenv("STEAM_OPENID_REALM", "http://localhost:5173").rstrip("/")


def resolve_steam_openid_urls(request: Request) -> tuple[str, str]:
    """Return (realm, return_to) for the Steam OpenID redirect handshake."""
    realm_env = os.getenv("STEAM_OPENID_REALM", "").strip()
    return_env = os.getenv("STEAM_OPENID_RETURN_TO", "").strip()

    if realm_env and return_env:
        return (
            _force_http_for_local_dev(realm_env.rstrip("/")),
            _force_http_for_local_dev(return_env),
        )

    derived = resolve_public_base_url(request)
    if derived:
        derived = _force_http_for_local_dev(derived)
        return derived, f"{derived}{PUBLIC_STEAM_CALLBACK_PATH}"

    realm = _force_http_for_local_dev(
        (realm_env or "http://localhost:5173").rstrip("/")
    )
    return_to = return_env or f"{realm}{PUBLIC_STEAM_CALLBACK_PATH}"
    return realm, _force_http_for_local_dev(return_to)
