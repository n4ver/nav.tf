"""Stable UUID helpers for the Event aggregate."""

from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5

EVENT_NAMESPACE = NAMESPACE_URL


def stable_event_uuid_from_slug(slug: str) -> UUID:
    normalized = (slug or "").strip().lower() or "default-event"
    return uuid5(EVENT_NAMESPACE, f"tf2-event-slug:{normalized}")
