"""Unit tests for shared CORS configuration."""

from __future__ import annotations

from cqrs.shared.cors import _allowed_origins


def test_allowed_origins_uses_cors_origins_env(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.example, http://b.example")
    assert _allowed_origins() == ["http://a.example", "http://b.example"]
