"""Unit tests for UTC/time helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from cqrs.shared.timeutils import ensure_utc_naive, parse_utc_naive, utcnow


def test_utcnow_returns_naive_datetime():
    value = utcnow()
    assert value.tzinfo is None


def test_ensure_utc_naive_keeps_naive_datetime():
    naive = datetime(2026, 1, 1, 8, 30) # noqa: DTZ001
    assert ensure_utc_naive(naive) == naive


def test_parse_utc_naive_accepts_datetime():
    naive = datetime(2026, 6, 15, 12, 0) # noqa: DTZ001
    assert parse_utc_naive(naive) == naive
    aware = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
    naive = ensure_utc_naive(aware)
    assert naive.tzinfo is None
    assert naive.hour == 12


def test_parse_utc_naive_from_iso_string():
    parsed = parse_utc_naive("2026-07-28T00:00:00Z")
    assert parsed.year == 2026
    assert parsed.tzinfo is None


def test_parse_utc_naive_fallback_for_unknown_input():
    parsed = parse_utc_naive(None)
    assert isinstance(parsed, datetime)
    assert parsed.tzinfo is None
