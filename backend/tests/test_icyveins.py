"""Tests for the Icy Veins BiS page parser (against the saved fixture)."""

from pathlib import Path

import pytest

from app.icyveins import ParseError, parse_bis_page

FIXTURE = Path(__file__).parent / "fixtures" / "brewmaster_bis.html"


@pytest.fixture(scope="module")
def parsed():
    html = FIXTURE.read_text(encoding="utf-8")
    items, max_ilvl, tips = parse_bis_page(html)
    return items, max_ilvl, tips


def test_all_populated_slots_parsed(parsed):
    items, _, _ = parsed
    slots = {item.slot for item in items}
    expected = {
        "head", "neck", "shoulders", "back", "chest", "wrist", "hands",
        "waist", "legs", "feet", "ring_1", "ring_2", "trinket_1",
        "trinket_2", "main_hand",
    }
    assert slots == expected
    assert "off_hand" not in slots  # empty off-hand is skipped


def test_expected_item_ids(parsed):
    items, _, _ = parsed
    by_slot = {item.slot: item.item_id for item in items}
    assert by_slot["head"] == 250015
    assert by_slot["hands"] == 250016
    assert by_slot["neck"] == 268291
    assert by_slot["waist"] == 268286
    assert by_slot["shoulders"] == 250013
    assert by_slot["cloak_legs" if "cloak_legs" in by_slot else "legs"] == by_slot["legs"]
    assert by_slot["main_hand"] == 249302


def test_ring_and_trinket_positional(parsed):
    items, _, _ = parsed
    by_slot = {item.slot: item.item_id for item in items}
    assert by_slot["ring_1"] == 249336
    assert by_slot["ring_2"] == 251513
    assert by_slot["trinket_1"] == 249343
    assert by_slot["trinket_2"] == 260235


def test_track_extracted_from_bonus_ids(parsed):
    items, _, _ = parsed
    by_slot = {item.slot: item for item in items}
    assert by_slot["head"].track == "Mythic Raid"  # bonus 13786
    assert by_slot["hands"].track == "Mythic+"  # bonus 12806


def test_drop_source_text(parsed):
    items, _, _ = parsed
    by_slot = {item.slot: item for item in items}
    assert "Catalyst" in by_slot["head"].drop
    assert "Rotmire" in by_slot["head"].drop
    assert any("dungeon-guide" in link for link in by_slot["legs"].drop_links)


def test_max_ilvl_and_tips(parsed):
    _, max_ilvl, tips = parsed
    assert max_ilvl == 289
    assert len(tips) == 2
    titles = {tip.title for tip in tips}
    assert "Which Dungeons Should I Farm?" in titles


def test_empty_html_raises():
    with pytest.raises(ParseError):
        parse_bis_page("<html><body><p>nothing here</p></body></html>")
