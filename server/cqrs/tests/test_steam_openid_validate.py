"""Unit tests for Steam OpenID callback validation."""

from __future__ import annotations

import asyncio

import pytest

from cqrs.shared.auth.steam_openid import SteamOpenIdClient


class FakeValidResponse:
    text = "ns:http://specs.openid.net/auth/2.0\nis_valid:true\n"

    def raise_for_status(self) -> None:
        return None


class FakeInvalidResponse:
    text = "is_valid:false\n"

    def raise_for_status(self) -> None:
        return None


class FakeHttpClient:
    def __init__(self, response: FakeValidResponse | FakeInvalidResponse) -> None:
        self.response = response
        self.last_data: dict | None = None

    async def post(
        self, _url: str, data: dict
    ) -> FakeValidResponse | FakeInvalidResponse:
        self.last_data = data
        return self.response

    async def aclose(self) -> None:
        return None


def _callback_params() -> dict[str, str]:
    return {
        "openid.mode": "id_res",
        "openid.claimed_id": "https://steamcommunity.com/openid/id/76561198000000001",
        "openid.identity": "https://steamcommunity.com/openid/id/76561198000000001",
        "openid.sig": "abc",
    }


def test_validate_callback_success():
    http = FakeHttpClient(FakeValidResponse())
    client = SteamOpenIdClient(http_client=http)

    steam_id = asyncio.run(client.validate_callback(_callback_params()))
    assert steam_id == "76561198000000001"
    assert http.last_data is not None
    assert http.last_data["openid.mode"] == "check_authentication"


def test_validate_callback_rejects_unexpected_mode():
    client = SteamOpenIdClient(http_client=FakeHttpClient(FakeValidResponse()))
    params = _callback_params()
    params["openid.mode"] = "cancel"

    with pytest.raises(ValueError, match="Unexpected OpenID mode"):
        asyncio.run(client.validate_callback(params))


def test_validate_callback_rejects_missing_steam_id():
    client = SteamOpenIdClient(http_client=FakeHttpClient(FakeValidResponse()))
    params = _callback_params()
    params["openid.claimed_id"] = "https://example.com/not-steam"

    with pytest.raises(ValueError, match="Could not extract SteamID"):
        asyncio.run(client.validate_callback(params))


def test_validate_callback_rejects_invalid_assertion():
    client = SteamOpenIdClient(http_client=FakeHttpClient(FakeInvalidResponse()))

    with pytest.raises(ValueError, match="assertion failed"):
        asyncio.run(client.validate_callback(_callback_params()))


def test_validate_callback_closes_internal_http_client(monkeypatch):
    closed = {"called": False}

    class FakeResponse:
        text = "is_valid:true\n"

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        async def post(
            self, _url: str, data: dict | None = None, **_kwargs
        ) -> FakeResponse:
            return FakeResponse()

        async def aclose(self) -> None:
            closed["called"] = True

    monkeypatch.setattr(
        "cqrs.shared.auth.steam_openid.httpx.AsyncClient",
        lambda **_kwargs: FakeClient(),
    )

    client = SteamOpenIdClient()
    steam_id = asyncio.run(client.validate_callback(_callback_params()))
    assert steam_id == "76561198000000001"
    assert closed["called"] is True
