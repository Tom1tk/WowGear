"""Tests for the Icy Veins BiS page parser (against the saved fixture)."""

from pathlib import Path

import pytest

from app.icyveins import ParseError, parse_bis_page

FIXTURE = Path(__file__).parent / "fixtures" / "brewmaster_bis.html"
S2_FIXTURE = Path(__file__).parent / "fixtures" / "frost_mage_bis_s2.html"


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


def test_bonus_ids_stored_on_item():
    items, _, _ = parse_bis_page(
        (FIXTURE.parent / "brewmaster_bis.html").read_text(encoding="utf-8")
    )
    by_slot = {item.slot: item for item in items}
    assert by_slot["waist"].bonus == [13786]
    assert by_slot["neck"].bonus == [13786]


def test_bonus_string_with_empty_segments_does_not_crash():
    html = (
        '<div id="bis_0_0">'
        '<div class="bis_item">'
        '<span class="bis_item_slot">Head</span>'
        '<span class="q4" data-wowhead="item=12345&amp;bonus=1111::2222">BiS Helm</span>'
        '<span class="bis_item_drop">Drops from Rotmire</span>'
        "</div></div>"
    )
    items, _, _ = parse_bis_page(html)
    assert len(items) == 1
    assert items[0].item_id == 12345
    assert items[0].track is None


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


# ── Midnight Season 2 pages ────────────────────────────────────────────

@pytest.fixture(scope="module")
def s2_parsed():
    html = S2_FIXTURE.read_text(encoding="utf-8")
    return parse_bis_page(html)


def test_s2_items_parsed(s2_parsed):
    items, _, _ = s2_parsed
    assert len(items) == 16
    slots = {item.slot for item in items}
    assert {"main_hand", "off_hand", "ring_1", "ring_2", "trinket_1", "trinket_2"} <= slots


def test_s2_track_derived_from_drop_links(s2_parsed):
    """Season 2 items carry multipart version bonus ids (not track ids), so
    the track comes from the drop-source guide link instead."""
    items, _, _ = s2_parsed
    by_slot = {item.slot: item for item in items}
    assert by_slot["head"].track == "Mythic Raid"   # ulatek-raid-guide
    assert by_slot["neck"].track == "Mythic Raid"   # ulatek-raid-guide
    assert by_slot["legs"].track == "Mythic+"       # kings-rest-dungeon-guide
    assert by_slot["wrist"].track == "Mythic+"      # den-of-nalorakk-dungeon-guide
    assert by_slot["waist"].track is None           # crafted (professions link)
    assert by_slot["trinket_2"].track is None       # midnight-world-bosses guide


def test_s2_multipart_bonus_ids_preserved(s2_parsed):
    items, _, _ = s2_parsed
    by_slot = {item.slot: item for item in items}
    assert 13848 in by_slot["head"].bonus
    assert 12854 in by_slot["legs"].bonus
    assert by_slot["legs"].bonus == [12854]


def test_s2_faq_tips(s2_parsed):
    _, _, tips = s2_parsed
    titles = {tip.title for tip in tips}
    assert len(tips) == 2
    assert "Which Dungeons Should I Farm?" in titles
    assert "What Raid Items Are Most Important?" in titles


def test_s2_max_ilvl_not_stated_falls_back_to_ceiling(s2_parsed):
    _, max_ilvl, _ = s2_parsed
    assert max_ilvl == 0  # page omits it; the season config default (334) is used
