"""Tests for public URL resolution used by Steam OpenID."""

from __future__ import annotations

from cqrs.shared.auth.urls import _force_http_for_local_dev, resolve_steam_openid_urls


class _FakeRequest:
    def __init__(self, headers: dict[str, str], scheme: str = "http") -> None:
        self.headers = headers
        self.url = type("URL", (), {"scheme": scheme})()


def test_force_http_for_localhost_https():
    assert (
        _force_http_for_local_dev("https://localhost:5173") == "http://localhost:5173"
    )
    assert (
        _force_http_for_local_dev("https://127.0.0.1:8001") == "http://127.0.0.1:8001"
    )


def test_resolve_steam_openid_urls_from_forwarded_headers(monkeypatch):
    monkeypatch.delenv("STEAM_OPENID_REALM", raising=False)
    monkeypatch.delenv("STEAM_OPENID_RETURN_TO", raising=False)
    request = _FakeRequest(
        {
            "X-Forwarded-Host": "localhost:5173",
            "X-Forwarded-Proto": "http",
        }
    )
    realm, return_to = resolve_steam_openid_urls(request)
    assert realm == "http://localhost:5173"
    assert return_to == "http://localhost:5173/api/auth/steam/callback"


def test_localhost_https_is_kept_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    assert _force_http_for_local_dev("https://localhost") == "https://localhost"
    monkeypatch.setenv("STEAM_OPENID_REALM", "https://localhost")
    monkeypatch.setenv(
        "STEAM_OPENID_RETURN_TO", "https://localhost/api/auth/steam/callback"
    )
    realm, return_to = resolve_steam_openid_urls(_FakeRequest({}))
    assert realm == "https://localhost"
    assert return_to == "https://localhost/api/auth/steam/callback"
