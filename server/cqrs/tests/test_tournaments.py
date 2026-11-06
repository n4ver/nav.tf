"""Unit tests for tournament catalog helpers."""

from __future__ import annotations

from cqrs.shared.tournaments import (
    build_tournament_command_from_slug,
    stable_tournament_uuid,
    stable_tournament_uuid_from_slug,
)


def test_stable_tournament_uuid_from_slug_uses_catalog_id():
    catalog_uuid = stable_tournament_uuid(1)
    slug_uuid = stable_tournament_uuid_from_slug("invite-bracket")
    assert slug_uuid == catalog_uuid


def test_build_tournament_command_from_slug_uses_catalog_metadata():
    command = build_tournament_command_from_slug("qualifier-bracket")
    assert command.slug == "qualifier-bracket"
    assert command.name == "Qualifier Bracket"
