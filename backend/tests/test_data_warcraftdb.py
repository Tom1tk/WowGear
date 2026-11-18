"""Tooltip parser (scripts/data/parse_warcraftdb.py) on synthetic tooltips."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "data"))

import parse_warcraftdb as pw  # noqa: E402


def line(text, kind="captured-none"):
    return f'<tt-line data-line-type="{kind}">{text}</tt-line>'


def double(a, b):
    return f"<tt-double-line><span>{a}</span><span>{b}</span></tt-double-line>"


ARMOR = ('<tt-title data-quality="3">Test Helm</tt-title>'
         + line("Item Level 40", "item-level") + line("Binds when picked up", "binding")
         + line("Unique", "unique") + double("Head", "Mail")
         + line('Classes: <span class="x">Hunter</span>, <span>Shaman</span>', "classes")
         + line("120 Armor", "armor") + line("+12 Agility", "item-stat") + line("+7 Stamina", "item-stat")
         + line("+5 Fire Resistance")
         + line("Equip: Increases attack power by 20.", "item-effect")
         + line("Equip: Improves your chance to hit by 1.0%.", "item-effect")
         + line("Equip: Increases your critical strike by 14.", "item-effect")
         + line("Equip: Does a mysterious thing.", "item-effect")
         + line("Durability 50 / 50", "durability") + line("Requires Level 38", "required-level")
         + line("Sell Price: 5", "item-price") + line("Totally new line type"))


def test_armor_tooltip():
    r = pw.parse_tooltip(ARMOR)
    assert r["inventory_type"] == "HEAD" and r["type_name"] == "Mail"
    assert r["binding"] == "ON_ACQUIRE" and r["unique"] is True
    assert r["classes"] == [3, 7] and r["required_level"] == 38 and r["item_level"] == 40
    assert r["stats"] == {"armor": 120, "agi": 12, "sta": 7, "res_fire": 5,
                          "ap": 20, "hit": 1.0, "crit_rating": 14}
    assert "Equip: Does a mysterious thing." in r["effects"]
    assert r["unparsed_effects"] == ["Equip: Does a mysterious thing."]  # never dropped silently
    assert r["unknown_lines"] == ["Totally new line type"]


def test_weapon_and_set_lines():
    html = ('<tt-title data-quality="4">Test Axe</tt-title>' + double("Two-Hand", "Axe")
            + double("100 - 200 Damage", "Speed 3.00") + line("(50.0 damage per second)")
            + line("Test Set (1/2)", "captured-none")
            + line("  Test Axe", "captured-disabled-line") + line("  Test Cap", "captured-disabled-line")
            + line("(2) Set: +30 Attack Power.", "captured-disabled-line"))
    r = pw.parse_tooltip(html)
    assert r["inventory_type"] == "TWOHWEAPON"
    assert r["weapon"] == {"min": 100, "max": 200, "speed": 3.0, "dps": 50.0}
    assert r["set"] == {"name": "Test Set", "size": 2, "pieces": ["Test Axe", "Test Cap"],
                        "bonuses": [{"pieces": 2, "text": "+30 Attack Power."}]}
    assert r["unknown_lines"] == []


def test_normalize_maps_shield_ranged_and_subclass():
    node = {"data": {"name": "N", "quality": "Rare", "item_class": "Weapon", "item_subclass": "Crossbow",
                     "item_level": 30, "required_level": 25}}
    tip = {"html": '<tt-title data-quality="3">N</tt-title>' + double("Ranged", "Crossbow")}
    item = pw.normalize(node, tip, [])
    assert (item["inventory_type"], item["class"], item["subclass"], item["quality"]) == ("RANGEDRIGHT", 2, 18, "RARE")
    node = {"data": {"item_class": "Armor", "item_subclass": "Shield", "quality": "Common"}}
    tip = {"html": double("Off Hand", "Shield")}
    assert pw.normalize(node, tip, [])["inventory_type"] == "SHIELD"


def test_tab_rows_become_sources():
    drop = pw.parse_tab("dropped-by", [{"source_id": 5, "name": "Boss", "source_kind_label": "NPC",
                                        "chance": 11.1, "loot_type_label": "Loot", "quantity": "1"}])
    assert drop[0]["type"] == "drop" and drop[0]["chance"] == 11.1
    quest = pw.parse_tab("reward-from", [{"id": 9, "name": "Q", "zone": "Z", "zone_id": 3, "reward_type": "Choice"}])
    assert quest[0]["choice"] is True


def test_foreverdb_rows():
    import parse_foreverdb as pf
    rows = pf.parse_gear_sources("-- c\n1o|Test Tunic|q|s|a|11851||q^6^Quest^2^a^s~d^9^Boss^1^0^k\n")
    assert rows[60]["name"] == "Test Tunic" and rows[60]["classic_labelled"] is True
