"""Tests for the Armory HTML scraper (keyless fallback)."""

from pathlib import Path

import pytest

from app.armory import (
    ArmoryCharacterNotFoundError,
    ArmoryParseError,
    fetch_armory_page,
    parse_armory_page,
)

FIXTURE = Path(__file__).parent / "fixtures" / "armory_greyball.html"


def test_parse_character_summary():
    html = FIXTURE.read_text(encoding="utf-8")
    summary, equipped = parse_armory_page(html, "eu")
    assert summary.name == "Greyball"
    assert summary.realm == "draenor"
    assert summary.region == "eu"
    assert summary.level == 90
    assert summary.class_name == "Monk"
    assert summary.spec == "Brewmaster"
    assert summary.race == "Pandaren"
    assert summary.faction == "Alliance"
    assert summary.average_item_level == 277
    assert summary.achievement_points == 2280
    assert summary.mythic_plus_rating == 2292


def test_parse_all_gear_slots():
    html = FIXTURE.read_text(encoding="utf-8")
    summary, equipped = parse_armory_page(html, "eu")
    assert set(equipped) == {
        "head", "neck", "shoulders", "back", "chest", "wrist", "hands",
        "waist", "legs", "feet", "ring_1", "ring_2", "trinket_1",
        "trinket_2", "main_hand", "off_hand",
    }
    assert equipped["head"].item_id == 250015
    assert equipped["head"].name == "Fearsome Visage of Ra-den's Chosen"
    assert equipped["head"].ilvl == 276
    assert equipped["main_hand"].item_id == 258438
    assert equipped["main_hand"].name == "Blazing Sunclaws"


def test_parse_error_on_empty_html():
    with pytest.raises(ArmoryParseError):
        parse_armory_page("<html><body>no state here</body></html>", "eu")


def test_fetch_armory_page_not_found(monkeypatch):
    import asyncio

    import httpx

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            return httpx.Response(404, request=httpx.Request("GET", url))

    monkeypatch.setattr("app.armory.httpx.AsyncClient", FakeClient)
    with pytest.raises(ArmoryCharacterNotFoundError):
        asyncio.run(fetch_armory_page("eu", "draenor", "nobody"))


def test_fetch_armory_page_ok(monkeypatch):
    import asyncio

    import httpx

    html = FIXTURE.read_text(encoding="utf-8")

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            return httpx.Response(200, text=html, request=httpx.Request("GET", url))

    monkeypatch.setattr("app.armory.httpx.AsyncClient", FakeClient)
    page = asyncio.run(fetch_armory_page("eu", "draenor", "greyball"))
    assert "characterProfileInitialState" in page
