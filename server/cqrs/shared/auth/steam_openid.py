"""Lightweight Steam OpenID 2.0 login helpers (no python-openid dependency)."""

from __future__ import annotations

import os
import re
from urllib.parse import urlencode

import httpx

from .urls import PUBLIC_STEAM_CALLBACK_PATH

STEAM_OPENID_LOGIN = "https://steamcommunity.com/openid/login"
CLAIMED_ID_RE = re.compile(
    r"^https://steamcommunity\.com/openid/id/(\d{17})$",
    re.IGNORECASE,
)


def extract_steam_id_from_claimed_id(claimed_id: str) -> str | None:
    match = CLAIMED_ID_RE.match((claimed_id or "").strip())
    return match.group(1) if match else None


class SteamOpenIdClient:
    """Build Steam OpenID redirect URLs and validate callback assertions."""

    def __init__(
        self,
        *,
        realm: str | None = None,
        return_to: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.realm = (
            realm or os.getenv("STEAM_OPENID_REALM") or "http://localhost:5173"
        ).rstrip("/")
        self.return_to = (
            return_to
            or os.getenv("STEAM_OPENID_RETURN_TO")
            or f"{self.realm}{PUBLIC_STEAM_CALLBACK_PATH}"
        )
        self._client = http_client

    def build_login_url(self) -> str:
        params = {
            "openid.ns": "http://specs.openid.net/auth/2.0",
            "openid.mode": "checkid_setup",
            "openid.return_to": self.return_to,
            "openid.realm": self.realm,
            "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
            "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
        }
        return f"{STEAM_OPENID_LOGIN}?{urlencode(params)}"

    async def validate_callback(self, params: dict[str, str]) -> str:
        """Validate Steam OpenID response and return the SteamID64.

        Raises ValueError when the assertion is invalid or Steam ID cannot be parsed.
        """
        mode = params.get("openid.mode")
        if mode != "id_res":
            raise ValueError(f"Unexpected OpenID mode: {mode!r}")

        claimed_id = (
            params.get("openid.claimed_id") or params.get("openid.identity") or ""
        )
        steam_id = extract_steam_id_from_claimed_id(claimed_id)
        if not steam_id:
            raise ValueError("Could not extract SteamID from OpenID claimed_id")

        check_params = {
            key: value for key, value in params.items() if key.startswith("openid.")
        }
        check_params["openid.mode"] = "check_authentication"

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=15.0)
        try:
            response = await client.post(STEAM_OPENID_LOGIN, data=check_params)
            response.raise_for_status()
            body = response.text
        finally:
            if owns_client:
                await client.aclose()

        valid = any(
            line.strip().lower() == "is_valid:true" for line in body.splitlines()
        )
        if not valid:
            raise ValueError("Steam OpenID assertion failed validation")

        return steam_id
