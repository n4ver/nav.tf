"""Internal service-to-service auth for seeding and automation."""

from __future__ import annotations

import os


def seed_service_token() -> str:
    return os.getenv("SEED_SERVICE_TOKEN", "").strip()


def seed_actor_steam_id() -> str:
    return os.getenv("SEED_ACTOR_STEAM_ID", "76561198000000000").strip()


def is_seed_service_token(token: str) -> bool:
    expected = seed_service_token()
    return bool(expected) and token == expected
