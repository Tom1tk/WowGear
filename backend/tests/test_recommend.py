"""Tests for the rule-based recommendation engine."""

import pytest

from app.models import BisItem, EquippedItem
from app.recommend import analyze_gear, catchup_action

BIS_ILVL = 289


def bis(slot: str, item_id: int, name: str, drop: str = "", links=None) -> BisItem:
    return BisItem(
        slot=slot, item_id=item_id, name=name, ilvl=0, drop=drop,
        drop_links=links or [], gems=[],
    )


def equipped(slot: str, item_id: int, name: str, ilvl: int) -> EquippedItem:
    return EquippedItem(slot=slot, item_id=item_id, name=name, ilvl=ilvl)


BIS_ITEMS = [
    bis("head", 100, "BiS Helm"),
    bis("neck", 200, "BiS Neck", drop="Craft with Leatherworking",
        links=["//www.icy-veins.com/wow/professions-leatherworking"]),
    bis("shoulders", 300, "BiS Shoulders"),
    bis("chest", 400, "BiS Chest", drop="Dropped by Rotmire",
        links=["//www.icy-veins.com/wow/rotmire-raid-guide"]),
    bis("legs", 500, "BiS Legs", drop="Farm Seat of the Triumvirate",
        links=["//www.icy-veins.com/wow/seat-of-the-triumvirate-dungeon-guide"]),
    bis("trinket_1", 600, "BiS Trinket"),
    bis("main_hand", 700, "BiS Weapon"),
]

ALL_SLOTS = [item.slot for item in BIS_ITEMS]


def fill_matching(overrides: dict[str, EquippedItem]) -> dict[str, EquippedItem]:
    """Every BiS slot filled with the exact BiS item; `overrides` replaces specific slots."""
    base = {}
    for item in BIS_ITEMS:
        base[item.slot] = equipped(item.slot, item.item_id, item.name, BIS_ILVL)
    base.update(overrides)
    return base


def test_match_and_ahead_slots_produce_no_actions():
    equipped_items = fill_matching({
        "neck": equipped("neck", 999, "Better Random", 300),  # ahead
    })
    comparisons, actions = analyze_gear(equipped_items, BIS_ITEMS, BIS_ILVL)
    assert len(actions) == 0
    by_slot = {c.slot: c for c in comparisons}
    assert by_slot["head"].status == "match"
    assert by_slot["neck"].status == "ahead"


def test_empty_slot_is_urgent():
    equipped_items = fill_matching({})
    equipped_items.pop("shoulders")
    comparisons, actions = analyze_gear(equipped_items, BIS_ITEMS, BIS_ILVL)
    empty = next(c for c in comparisons if c.slot == "shoulders")
    assert empty.status == "empty"
    assert empty.ilvl_gap == 289
    assert any("Fill empty shoulders" in a.title for a in actions)


def test_upgrade_prioritized_by_gap_and_slot_weight():
    equipped_items = fill_matching({
        "chest": equipped("chest", 401, "Old Chest", 270),  # gap 19, weight 1.2
        "main_hand": equipped("main_hand", 701, "Old Weapon", 280),  # gap 9, weight 1.5
        "legs": equipped("legs", 501, "Old Legs", 260),  # gap 29, weight 1.2
    })
    comparisons, actions = analyze_gear(equipped_items, BIS_ITEMS, BIS_ILVL)
    ordered = [a.slot for a in actions]
    assert ordered == ["legs", "chest", "main_hand"]
    leg_action = next(a for a in actions if a.slot == "legs")
    assert "Seat of the Triumvirate" in leg_action.detail
    assert "Mythic+" in leg_action.detail


def test_different_action_templates():
    equipped_items = fill_matching({
        "neck": equipped("neck", 201, "Old Neck", 250),
        "chest": equipped("chest", 401, "Old Chest", 250),
        "legs": equipped("legs", 501, "Old Legs", 250),
    })
    _, actions = analyze_gear(equipped_items, BIS_ITEMS, BIS_ILVL)
    by_slot = {a.slot: a for a in actions}
    assert "Leatherworking" in by_slot["neck"].detail  # crafted
    assert "Kill Rotmire" in by_slot["chest"].detail  # raid boss
    assert "Seat of the Triumvirate" in by_slot["legs"].detail  # dungeon


def test_same_item_lower_ilvl_is_upgrade_category():
    equipped_items = fill_matching({"head": equipped("head", 100, "BiS Helm", 277)})
    _, actions = analyze_gear(equipped_items, BIS_ITEMS, BIS_ILVL)
    assert len(actions) == 1
    action = actions[0]
    assert action.category == "upgrade"
    assert action.title == "Upgrade your BiS Helm (277 -> 289)"


def test_catchup_action_only_when_below_max():
    action = catchup_action(avg_ilvl=277, bis_max_ilvl=289)
    assert action is not None
    assert action.category == "catchup"
    assert action.urgency == pytest.approx(12 * 0.25)
    assert catchup_action(avg_ilvl=289, bis_max_ilvl=289) is None
    assert catchup_action(avg_ilvl=None, bis_max_ilvl=289) is None
