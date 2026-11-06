"""Canonical tournament definitions for invite.txt bracket groupings."""

from __future__ import annotations

from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from .schemas import TournamentCommandModel

TOURNAMENT_NAMESPACE = NAMESPACE_URL

# Section headers in invite.txt -> catalog tournament id
TOURNAMENT_SECTION_MAP: dict[str, int] = {
    "invite": 1,
    "qualifiers": 2,
    "R8": 2,
    "R7": 2,
    "R6": 2,
    "R5": 2,
    "R4": 2,
    "R3": 2,
    "R2": 2,
    "R1": 2,
    "main": 3,
}

TOURNAMENT_CATALOG: dict[int, dict[str, str]] = {
    1: {"name": "Invite Bracket", "slug": "invite-bracket"},
    2: {"name": "Qualifier Bracket", "slug": "qualifier-bracket"},
    3: {"name": "Main Bracket", "slug": "main-bracket"},
    4: {"name": "Matcha.tf Minicup Invite", "slug": "matcha-tf-minicup-invite"},
}

DEFAULT_TOURNAMENT_SLUG = "default-tournament"
DEFAULT_TOURNAMENT_NAME = "Default Tournament"

CATALOG_SLUGS = {meta["slug"] for meta in TOURNAMENT_CATALOG.values()}
VISIBLE_TOURNAMENT_SLUGS = CATALOG_SLUGS | {DEFAULT_TOURNAMENT_SLUG}


def stable_tournament_uuid(catalog_id: int) -> UUID:
    return uuid5(TOURNAMENT_NAMESPACE, f"tf2-tournament:{catalog_id}")


def stable_tournament_uuid_from_slug(slug: str) -> UUID:
    normalized = (slug or "").strip().lower() or DEFAULT_TOURNAMENT_SLUG
    # Preserve catalog UUIDs for known catalog slugs.
    for catalog_id, meta in TOURNAMENT_CATALOG.items():
        if meta["slug"] == normalized:
            return stable_tournament_uuid(catalog_id)
    return uuid5(TOURNAMENT_NAMESPACE, f"tf2-tournament-slug:{normalized}")


def build_tournament_command(
    catalog_id: int,
    start_date: datetime | None = None,
) -> TournamentCommandModel:
    meta = TOURNAMENT_CATALOG.get(
        catalog_id,
        {"name": f"Tournament {catalog_id}", "slug": f"tournament-{catalog_id}"},
    )
    return TournamentCommandModel(
        tournament_id=stable_tournament_uuid(catalog_id),
        name=meta["name"],
        slug=meta["slug"],
        start_date=start_date,
    )


def builtin_tournament_command(tournament_id: str) -> TournamentCommandModel | None:
    """Definition of a built-in tournament (catalog bracket or the default one) by id.

    Ingest attaches matches to these without creating a write-side record, so the
    read model lists them even though the command side has never stored them.
    """
    for catalog_id in TOURNAMENT_CATALOG:
        if str(stable_tournament_uuid(catalog_id)) == tournament_id:
            return build_tournament_command(catalog_id)
    if str(stable_tournament_uuid_from_slug(DEFAULT_TOURNAMENT_SLUG)) == tournament_id:
        return build_tournament_command_from_slug(DEFAULT_TOURNAMENT_SLUG)
    return None


def build_tournament_command_from_slug(
    slug: str,
    name: str | None = None,
    start_date: datetime | None = None,
) -> TournamentCommandModel:
    normalized = (slug or "").strip().lower() or DEFAULT_TOURNAMENT_SLUG
    for meta in TOURNAMENT_CATALOG.values():
        if meta["slug"] == normalized:
            return TournamentCommandModel(
                tournament_id=stable_tournament_uuid_from_slug(normalized),
                name=meta["name"],
                slug=meta["slug"],
                start_date=start_date,
            )
    display_name = name or (
        DEFAULT_TOURNAMENT_NAME
        if normalized == DEFAULT_TOURNAMENT_SLUG
        else normalized.replace("-", " ").title()
    )
    return TournamentCommandModel(
        tournament_id=stable_tournament_uuid_from_slug(normalized),
        name=display_name,
        slug=normalized,
        start_date=start_date,
    )
