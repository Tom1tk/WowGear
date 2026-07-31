"""Tests for the Blizzard API client using a mock HTTP transport."""

import asyncio

import httpx
import pytest

from app.blizzard import (
    ApiKeyInvalidError,
    ApiKeyMissingError,
    ApiUnavailableError,
    BlizzardClient,
    BlizzardError,
    CharacterNotFoundError,
    RateLimitedError,
)

TOKEN_RESPONSE = {"access_token": "test-token", "token_type": "bearer", "expires_in": 86400}


def profile_response() -> dict:
    return {
        "name": "Greyball",
        "realm": {"slug": "draenor", "name": "Draenor"},
        "faction": {"name": "Alliance"},
        "race": {"name": "Pandaren"},
        "character_class": {"name": "Monk"},
        "specialization": {"name": "Brewmaster"},
        "level": 90,
        "achievement_points": 2280,
        "average_item_level": 277,
    }


def equipment_response() -> dict:
    return {
        "equipped_items": [
            {
                "item": {"id": 250015, "name": "Fearsome Visage of Ra-den's Chosen"},
                "slot": {"type": "HEAD", "name": "Head"},
                "level": {"value": 276, "display_string": "276"},
                "quality": {"name": "Epic"},
            }
        ]
    }


def make_client(handler) -> BlizzardClient:
    transport = httpx.MockTransport(handler)
    return BlizzardClient("id", "secret", transport=transport)


def run(coro):
    return asyncio.run(coro)


def test_token_cached_between_requests():
    token_calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth.battle.net":
            token_calls["count"] += 1
            return httpx.Response(200, json=TOKEN_RESPONSE)
        return httpx.Response(200, json=profile_response())

    client = make_client(handler)
    summary = run(client.character_summary("eu", "draenor", "greyball"))
    assert summary.name == "Greyball"
    assert summary.class_name == "Monk"
    assert summary.spec == "Brewmaster"
    assert summary.average_item_level == 277
    run(client.character_summary("eu", "draenor", "greyball"))
    assert token_calls["count"] == 1


def test_equipment_slot_mapping():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth.battle.net":
            return httpx.Response(200, json=TOKEN_RESPONSE)
        return httpx.Response(200, json=equipment_response())

    client = make_client(handler)
    equipped = run(client.equipment("eu", "draenor", "greyball"))
    assert equipped["head"].item_id == 250015
    assert equipped["head"].ilvl == 276
    assert equipped["head"].quality == "Epic"


def test_character_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth.battle.net":
            return httpx.Response(200, json=TOKEN_RESPONSE)
        return httpx.Response(404, json={"code": 404, "detail": "Not Found"})

    client = make_client(handler)
    with pytest.raises(CharacterNotFoundError):
        run(client.character_summary("eu", "draenor", "nobody"))


def test_empty_404_raises_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth.battle.net":
            return httpx.Response(200, json=TOKEN_RESPONSE)
        return httpx.Response(404, text="", request=httpx.Request("GET", str(request.url)))

    client = make_client(handler)
    with pytest.raises(ApiUnavailableError):
        run(client.character_summary("eu", "draenor", "greyball"))


def test_invalid_credentials():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth.battle.net":
            return httpx.Response(401, json={"error": "invalid_client"})
        return httpx.Response(200, json={})

    client = make_client(handler)
    with pytest.raises(ApiKeyInvalidError):
        run(client.character_summary("eu", "draenor", "greyball"))


def test_rate_limited():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth.battle.net":
            return httpx.Response(200, json=TOKEN_RESPONSE)
        return httpx.Response(429, json={"code": 429, "detail": "rate limited"})

    client = make_client(handler)
    with pytest.raises(RateLimitedError):
        run(client.character_summary("eu", "draenor", "greyball"))


def test_missing_credentials_raises_friendly_error():
    client = BlizzardClient("", "")
    with pytest.raises(ApiKeyMissingError):
        run(client.character_summary("eu", "draenor", "greyball"))


def test_mythic_rating_failure_is_non_fatal():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth.battle.net":
            return httpx.Response(200, json=TOKEN_RESPONSE)
        if "mythic-keystone-profile" in str(request.url):
            return httpx.Response(500, json={})
        return httpx.Response(200, json=profile_response())

    client = make_client(handler)
    summary = run(client.character_summary("eu", "draenor", "greyball"))
    assert summary.mythic_plus_rating is None


def test_unexpected_error_is_wrapped():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth.battle.net":
            return httpx.Response(200, json=TOKEN_RESPONSE)
        return httpx.Response(500, json={})

    client = make_client(handler)
    with pytest.raises(BlizzardError):
        run(client.character_summary("eu", "draenor", "greyball"))
