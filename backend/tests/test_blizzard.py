"""Blizzard Forever client: parsing and HTTP behaviour (mock transport)."""

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
    parse_ruleset,
    parse_talents,
)

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text())


def test_parse_equipment_maps_forever_slots():
    eq = parse_equipment(load("forever_equipment.json"))
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
    trees = parse_talents(load("forever_specializations.json"))
    assert [(t.name, t.points) for t in trees] == [("Fury", 34), ("Arms", 17)]


def mock_client(handler):
    return BlizzardClient("id", "secret", transport=httpx.MockTransport(handler))


def ok_handler(seen, media=True, profile=None):
    def handler(request: httpx.Request):
        if request.url.host == "oauth.battle.net":
            return httpx.Response(200, json={"access_token": "t"})
        seen.append((request.url.raw_path.decode().split("?")[0], request.url.params["namespace"]))
        path = request.url.path
        if path.endswith("/equipment"):
            return httpx.Response(200, json=load("forever_equipment.json"))
        if path.endswith("/specializations"):
            return httpx.Response(200, json=load("forever_specializations.json"))
        if path.endswith("/character-media"):
            if not media:
                return httpx.Response(404, json={"code": 404})
            return httpx.Response(200, json={"assets": [{"key": "avatar", "value": "https://x/a.jpg"}]})
        return httpx.Response(200, json=profile or load("forever_profile.json"))
    return handler


def test_character_url_and_namespace():
    seen = []
    summary, equipped, talents = asyncio.run(
        mock_client(ok_handler(seen)).character("us", "Testa", "Exampleton"))
    assert {ns for _, ns in seen} == {"profile-forever-us"}
    assert seen[0][0] == "/profile/wow/character/testa-exampleton"
    assert summary.level == 60 and summary.class_id == 1 and summary.faction == "H"
    assert summary.surname == "Exampleton" and summary.ruleset == "Normal"
    assert summary.guild == "Example Guild" and summary.avatar_url == "https://x/a.jpg"
    assert len(equipped) >= 16 and talents[0].name == "Fury"


def test_character_url_encodes_accents():
    seen = []
    asyncio.run(mock_client(ok_handler(seen)).character("eu", "Zoë", "Müller"))
    assert seen[0][0] == "/profile/wow/character/zo%C3%AB-m%C3%BCller"


def test_character_without_media_is_fine():
    summary, _, _ = asyncio.run(mock_client(ok_handler([], media=False)).character("us", "testa", "exampleton"))
    assert summary.avatar_url is None


def test_ruleset_shapes():
    assert parse_ruleset({"id": 1, "name": "PvP"}) == "PvP"
    assert parse_ruleset({"key": {"href": "https://x"}, "name": "RP", "id": 2}) == "RP"
    assert parse_ruleset("Normal") == "Normal"
    assert parse_ruleset(None) is None and parse_ruleset({"id": 3}) is None


def test_profile_without_ruleset_or_spec():
    profile = load("forever_profile.json")
    del profile["ruleset"]
    summary, _, _ = asyncio.run(mock_client(ok_handler([], profile=profile)).character("us", "testa", "exampleton"))
    assert summary.ruleset is None


def test_parse_talents_retail_like_and_unknown_shapes():
    retail = {"specializations": [
        {"specialization": {"name": "Arms"}, "talents": [{}, {}]},
        {"specialization": {"name": "Fury"}, "talents": [{}, {}, {}]},
    ]}
    assert [(t.name, t.points) for t in parse_talents(retail)] == [("Arms", 2), ("Fury", 3)]
    assert [(t.name, t.points) for t in parse_talents({"active_specialization": {"name": "Fury"}})] == [("Fury", 1)]
    assert parse_talents({"something": "else"}) == []


def test_character_not_found_message():
    def handler(request):
        if request.url.host == "oauth.battle.net":
            return httpx.Response(200, json={"access_token": "t"})
        return httpx.Response(404, json={"code": 404})

    with pytest.raises(CharacterNotFoundError, match="from level 10, after logging out"):
        asyncio.run(mock_client(handler).character("eu", "nobody", "nobody"))


def test_missing_key():
    client = BlizzardClient("", "")
    with pytest.raises(ApiKeyMissingError):
        asyncio.run(client.character("eu", "x", "y"))


def test_parse_equipment_reads_worn_stats():
    data = {"equipped_items": [{
        "item": {"id": 990001}, "name": "Invented Boots of the Tiger", "slot": {"type": "FEET"},
        "inventory_type": {"type": "FEET"}, "quality": {"type": "UNCOMMON"},
        "item_class": {"id": 4}, "item_subclass": {"id": 2}, "armor": {"value": 59},
        "stats": [{"type": {"type": "AGILITY"}, "value": 4}, {"type": {"type": "STRENGTH"}, "value": 4},
                  {"type": {"type": "EXTRA_ARMOR"}, "value": 10, "is_equip_bonus": True},
                  {"type": {"type": "STAMINA"}, "value": 2, "is_negated": True}],
    }]}
    worn = parse_equipment(data)["feet"].worn
    assert worn.item_class == 4 and worn.weapon is None
    assert worn.stats == {"agi": 4, "str": 4, "bonus_armor": 10, "armor": 59}
