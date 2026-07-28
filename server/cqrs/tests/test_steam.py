import asyncio

from cqrs.shared.steam import SteamWebApiClient, canonical_steam_id, to_steam_id64


def test_to_steam_id64_formats():
    assert to_steam_id64("[U:1:12345]") == str(76561197960265728 + 12345)
    assert to_steam_id64("STEAM_0:1:12345") == str(76561197960265728 + 12345 * 2 + 1)
    assert to_steam_id64("76561198000000000") == "76561198000000000"
    assert to_steam_id64("not-a-steam-id") is None


def test_canonical_steam_id_normalizes_legacy_formats():
    assert canonical_steam_id("STEAM_0:1:12345") == to_steam_id64("STEAM_0:1:12345")
    assert canonical_steam_id("76561198000000000") == "76561198000000000"
    assert canonical_steam_id("BOT") == "BOT"


def test_steam_api_batch_mocked():
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "response": {
                    "players": [
                        {
                            "steamid": "76561197960278073",
                            "personaname": "ScoutMain",
                            "avatar": "https://example.com/a.jpg",
                        }
                    ]
                }
            }

    class FakeClient:
        async def get(self, *args, **kwargs):
            return FakeResponse()

        async def aclose(self):
            return None

    client = SteamWebApiClient(api_key="test-key", http_client=FakeClient())
    result = asyncio.run(client.get_player_summaries(["[U:1:12345]"]))
    assert "76561197960278073" in result
    assert result["76561197960278073"]["personaname"] == "ScoutMain"
