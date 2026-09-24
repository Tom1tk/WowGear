"""Blizzard Era client: parsing and HTTP behaviour (mock transport)."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from app.blizzard import (
    ApiKeyMissingError,
    BlizzardClient,
    CharacterNotFoundError,
    parse_equipment,
    parse_talents,
)

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text())


def test_parse_equipment_maps_era_slots():
    eq = parse_equipment(load("era_equipment.json"))
    assert "ranged" in eq  # Classic has a ranged / relic slot
    assert "shirt" not in eq and "tabard" not in eq
    assert eq["ring_1"].item_id and eq["trinket_2"].item_id
    assert eq["head"].name == "Lionheart Helm"


def test_parse_equipment_two_hander_goes_to_two_hand_slot():
    data = {"equipped_items": [{
        "item": {"id": 12784}, "name": "Arcanite Reaper", "slot": {"type": "MAIN_HAND"},
        "inventory_type": {"type": "TWOHWEAPON"}, "quality": {"type": "EPIC"},
    }]}
    eq = parse_equipment(data)
    assert "two_hand" in eq and "main_hand" not in eq


def test_parse_talents_uses_active_group():
    trees = parse_talents(load("era_specializations.json"))
    assert [(t.name, t.points) for t in trees] == [("Fury", 34), ("Arms", 17)]


def mock_client(handler):
    return BlizzardClient("id", "secret", transport=httpx.MockTransport(handler))


def test_character_uses_classic1x_namespace():
    seen = []

    def handler(request: httpx.Request):
        if request.url.host == "oauth.battle.net":
            return httpx.Response(200, json={"access_token": "t"})
        seen.append(request.url.params["namespace"])
        path = request.url.path
        if path.endswith("/equipment"):
            return httpx.Response(200, json=load("era_equipment.json"))
        if path.endswith("/specializations"):
            return httpx.Response(200, json=load("era_specializations.json"))
        if path.endswith("/character-media"):
            return httpx.Response(200, json={"assets": [{"key": "avatar", "value": "https://x/a.jpg"}]})
        return httpx.Response(200, json=load("era_profile.json"))

    summary, equipped, talents = asyncio.run(mock_client(handler).character("us", "whitemane", "testchar"))
    assert set(seen) == {"profile-classic1x-us"}
    assert summary.level == 60 and summary.class_id == 1 and summary.faction == "H"
    assert summary.avatar_url == "https://x/a.jpg"
    assert len(equipped) >= 16 and talents[0].name == "Fury"


def test_character_not_found():
    def handler(request):
        if request.url.host == "oauth.battle.net":
            return httpx.Response(200, json={"access_token": "t"})
        return httpx.Response(404, json={"code": 404})

    with pytest.raises(CharacterNotFoundError):
        asyncio.run(mock_client(handler).character("eu", "firemaw", "nobody"))


def test_missing_key():
    client = BlizzardClient("", "")
    with pytest.raises(ApiKeyMissingError):
        asyncio.run(client.character("eu", "x", "y"))


def test_realms_skip_internal_test_realms():
    def handler(request):
        if request.url.host == "oauth.battle.net":
            return httpx.Response(200, json={"access_token": "t"})
        assert request.url.params["namespace"] == "dynamic-classic1x-eu"
        return httpx.Response(200, json={"realms": [
            {"name": "Soulseeker", "slug": "soulseeker"},
            {"name": "EU4 CWOW GMSS 1", "slug": "eu4-cwow-gmss-1"},
            {"name": "Mirage Raceway", "slug": "mirage-raceway"},
        ]})

    realms = asyncio.run(mock_client(handler).realms("eu"))
    assert [r["slug"] for r in realms] == ["mirage-raceway", "soulseeker"]
