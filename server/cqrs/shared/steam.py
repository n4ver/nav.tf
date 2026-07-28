"""Steam ID conversion and Web API helpers."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

STEAM_ID3_RE = re.compile(r"^\[U:(\d+):(\d+)\]$")
STEAM_ID_RE = re.compile(r"^STEAM_([0-5]):([01]):(\d+)$", re.IGNORECASE)
STEAM64_BASE = 76561197960265728
STEAM_API_URL = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"


def to_steam_id64(steam_id: str) -> str | None:
    """Convert SteamID3 / SteamID / SteamID64 to a 17-digit SteamID64 string."""
    value = (steam_id or "").strip()
    if not value:
        return None
    if value.isdigit() and len(value) == 17:
        return value

    match = STEAM_ID3_RE.match(value)
    if match:
        account_id = int(match.group(2))
        return str(STEAM64_BASE + account_id)

    match = STEAM_ID_RE.match(value)
    if match:
        y = int(match.group(2))
        z = int(match.group(3))
        account_id = z * 2 + y
        return str(STEAM64_BASE + account_id)

    return None


def canonical_steam_id(steam_id: str) -> str:
    """Return SteamID64 when parseable; otherwise preserve the original identifier."""
    value = (steam_id or "").strip()
    if not value:
        return value
    return to_steam_id64(value) or value


class SteamWebApiClient:
    """Thin client for Steam GetPlayerSummaries (batched, 100 IDs per call)."""

    def __init__(self, api_key: str | None = None, http_client: httpx.AsyncClient | None = None) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("STEAM_API_KEY", "").strip()
        self._client = http_client

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def get_player_summaries(self, steam_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Return mapping steam_id64 -> summary dict for resolved players."""
        if not self.enabled or not steam_ids:
            return {}

        unique_ids = []
        seen: set[str] = set()
        for raw in steam_ids:
            sid64 = to_steam_id64(raw) or (raw if raw.isdigit() else None)
            if not sid64 or sid64 in seen:
                continue
            seen.add(sid64)
            unique_ids.append(sid64)

        results: dict[str, dict[str, Any]] = {}
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=15.0)
        try:
            for offset in range(0, len(unique_ids), 100):
                batch = unique_ids[offset : offset + 100]
                response = await client.get(
                    STEAM_API_URL,
                    params={"key": self.api_key, "steamids": ",".join(batch)},
                )
                response.raise_for_status()
                payload = response.json()
                players = ((payload.get("response") or {}).get("players")) or []
                for player in players:
                    sid = str(player.get("steamid") or "")
                    if sid:
                        results[sid] = player
        except Exception:
            logger.exception("Steam GetPlayerSummaries failed")
            return results
        finally:
            if owns_client:
                await client.aclose()
        return results
