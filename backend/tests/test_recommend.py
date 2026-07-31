"""Tests for the rule-based recommendation engine."""

import pytest

from app.models import Action, BisItem, EquippedItem
from app.recommend import analyze_gear, catchup_action

BIS_ILVL = 289


def bis(slot: str, item_id: int, name: str, drop: str = "", links=None,
        link_texts=None, bonus=None) -> BisItem:
    return BisItem(
        slot=slot, item_id=item_id, name=name, ilvl=0, drop=drop,
        drop_links=links or [], drop_link_texts=link_texts or [],
        bonus=bonus or [], gems=[],
    )


def equipped(slot: str, item_id: int, name: str, ilvl: int,
             inventory_type: str | None = None) -> EquippedItem:
    return EquippedItem(
        slot=slot, item_id=item_id, name=name, ilvl=ilvl,
        inventory_type=inventory_type,
    )


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


def test_catchup_action_skipped_within_one_ilvl():
    assert catchup_action(avg_ilvl=288, bis_max_ilvl=289) is None


def test_catchup_action_mentions_current_systems():
    action = catchup_action(avg_ilvl=277, bis_max_ilvl=289)
    assert "Dawncrests" in action.detail
    assert "Great Vault" in action.detail


def test_two_handed_main_hand_suppresses_off_hand_advice():
    bis_items = BIS_ITEMS + [
        bis("off_hand", 800, "BiS Off Hand"),
    ]
    equipped_items = fill_matching({})
    equipped_items["main_hand"] = equipped(
        "main_hand", 701, "Old Staff", 280, inventory_type="TWOHWEAPON"
    )
    comparisons, actions = analyze_gear(equipped_items, bis_items, BIS_ILVL)
    off_hand = next(c for c in comparisons if c.slot == "off_hand")
    assert off_hand.status == "no_bis"
    assert not any(a.slot == "off_hand" for a in actions)


def test_one_handed_main_hand_keeps_off_hand_advice():
    bis_items = BIS_ITEMS + [
        bis("off_hand", 800, "BiS Off Hand"),
    ]
    equipped_items = fill_matching({})
    equipped_items["main_hand"] = equipped(
        "main_hand", 701, "Old Sword", 280, inventory_type="WEAPON"
    )
    comparisons, actions = analyze_gear(equipped_items, bis_items, BIS_ILVL)
    off_hand = next(c for c in comparisons if c.slot == "off_hand")
    assert off_hand.status == "empty"
    assert any(a.slot == "off_hand" for a in actions)


# ── Link segments ──────────────────────────────────────────────────────

# The real brewmaster fixture example: waist BiS from Rotmire.
WAIST_BIS = bis(
    "waist", 268286, "Sash of the Putrid Giant", drop="Rotmire",
    links=["//www.icy-veins.com/wow/rotmire-raid-guide"],
    link_texts=["Rotmire"], bonus=[13786],
)
WAIST_BIS.track = "Mythic Raid"


def segment_map(segments):
    """Return {text: url-or-None} preserving first-occurrence order."""
    return [(s.text, s.url) for s in segments]


def test_plain_text_of_segments_matches_title_and_detail():
    """Guarantee the visible text is unchanged: joining segments equals the
    plain title/detail strings for every action template."""
    equipped_items = fill_matching({
        "waist": equipped("waist", 9, "Twisted Twilight Sash", 263),
        "neck": equipped("neck", 201, "Old Neck", 250),
        "chest": equipped("chest", 401, "Old Chest", 250),
        "legs": equipped("legs", 501, "Old Legs", 250),
        "head": equipped("head", 100, "BiS Helm", 277),
        "trinket_1": equipped("trinket_1", 601, "Old Trinket", 250),
        "main_hand": equipped("main_hand", 701, "Old Weapon", 250),
    })
    _, actions = analyze_gear(
        equipped_items, BIS_ITEMS + [WAIST_BIS], BIS_ILVL
    )
    assert len(actions) >= 6
    for action in actions:
        assert action.title == "".join(s.text for s in action.title_segments)
        assert action.detail == "".join(s.text for s in action.detail_segments)


def test_replace_title_links_both_items():
    """Equipped item links to wowhead by id; BiS item link includes bonus ids."""
    equipped_items = fill_matching(
        {"waist": equipped("waist", 9, "Twisted Twilight Sash", 263)}
    )
    _, actions = analyze_gear(equipped_items, BIS_ITEMS + [WAIST_BIS], BIS_ILVL)
    action = next(a for a in actions if a.slot == "waist")
    segs = segment_map(action.title_segments)
    assert segs == [
        ("Replace waist: ", None),
        ("Twisted Twilight Sash", "https://www.wowhead.com/item=9/twisted-twilight-sash"),
        (" (263) -> ", None),
        ("Sash of the Putrid Giant",
         "https://www.wowhead.com/item=268286/sash-of-the-putrid-giant?bonus=13786"),
        (" (289)", None),
    ]


def test_fill_empty_title_links_bis_item():
    equipped_items = fill_matching({"waist": None})
    _, actions = analyze_gear(equipped_items, BIS_ITEMS + [WAIST_BIS], BIS_ILVL)
    action = next(a for a in actions if a.slot == "waist")
    segs = segment_map(action.title_segments)
    assert segs[0] == ("Fill empty waist: get ", None)
    assert segs[1][0] == "Sash of the Putrid Giant"
    assert segs[1][1].startswith("https://www.wowhead.com/item=268286/sash-of-the-putrid-giant")
    assert segs[2] == (" (289)", None)


def test_upgrade_title_links_bis_item():
    equipped_items = fill_matching(
        {"waist": equipped("waist", 268286, "Sash of the Putrid Giant", 277)}
    )
    _, actions = analyze_gear(equipped_items, BIS_ITEMS + [WAIST_BIS], BIS_ILVL)
    action = next(a for a in actions if a.slot == "waist")
    assert action.category == "upgrade"
    segs = segment_map(action.title_segments)
    assert segs[0] == ("Upgrade your ", None)
    assert segs[1] == (
        "Sash of the Putrid Giant",
        "https://www.wowhead.com/item=268286/sash-of-the-putrid-giant?bonus=13786",
    )
    assert segs[2] == (" (277 -> 289)", None)


def test_raid_boss_detail_links_boss_and_item():
    equipped_items = fill_matching(
        {"waist": equipped("waist", 9, "Twisted Twilight Sash", 263)}
    )
    _, actions = analyze_gear(equipped_items, BIS_ITEMS + [WAIST_BIS], BIS_ILVL)
    action = next(a for a in actions if a.slot == "waist")
    assert action.detail == (
        "Kill Rotmire in the current raid on Mythic difficulty to loot "
        "Sash of the Putrid Giant (289)."
    )
    segs = segment_map(action.detail_segments)
    assert segs[0] == ("Kill ", None)
    assert segs[1] == ("Rotmire", "//www.icy-veins.com/wow/rotmire-raid-guide")
    assert segs[2] == (" in the current raid on Mythic difficulty to loot ", None)
    assert segs[3] == (
        "Sash of the Putrid Giant",
        "https://www.wowhead.com/item=268286/sash-of-the-putrid-giant?bonus=13786",
    )
    assert segs[4] == (" (289).", None)


def test_dungeon_detail_links_dungeon_and_item():
    equipped_items = fill_matching(
        {"legs": equipped("legs", 501, "Old Legs", 260)}
    )
    _, actions = analyze_gear(equipped_items, BIS_ITEMS, BIS_ILVL)
    action = next(a for a in actions if a.slot == "legs")
    segs = segment_map(action.detail_segments)
    assert ("Farm ", None) in segs
    assert ("Seat of the Triumvirate",
            "//www.icy-veins.com/wow/seat-of-the-triumvirate-dungeon-guide") in segs
    assert segs[-2] == (
        "BiS Legs", "https://www.wowhead.com/item=500/bis-legs"
    )


def test_crafted_detail_links_profession_and_item():
    equipped_items = fill_matching(
        {"neck": equipped("neck", 201, "Old Neck", 250)}
    )
    _, actions = analyze_gear(equipped_items, BIS_ITEMS, BIS_ILVL)
    action = next(a for a in actions if a.slot == "neck")
    segs = segment_map(action.detail_segments)
    assert ("Leatherworking",
            "//www.icy-veins.com/wow/professions-leatherworking") in segs
    assert segs[-1] == (" — or buy it on the Auction House.", None)


def test_catalyst_detail_links_guide_and_item():
    wrist_bis = bis(
        "wrist", 777, "BiS Bracers", drop="Catalyst",
        links=["//www.icy-veins.com/wow/catalyst-guide"],
        link_texts=["Catalyst"], bonus=[13786],
    )
    equipped_items = fill_matching(
        {"wrist": equipped("wrist", 778, "Old Bracers", 250)}
    )
    _, actions = analyze_gear(equipped_items, BIS_ITEMS + [wrist_bis], BIS_ILVL)
    action = next(a for a in actions if a.slot == "wrist")
    assert action.detail == (
        "Convert a tier token at the Catalyst (see the Catalyst guide) — "
        "you need BiS Bracers (289)."
    )
    segs = segment_map(action.detail_segments)
    assert ("Catalyst guide", "//www.icy-veins.com/wow/catalyst-guide") in segs
    assert ("BiS Bracers",
            "https://www.wowhead.com/item=777/bis-bracers?bonus=13786") in segs


def test_item_linked_when_drop_has_no_guide_links():
    """Fallback detail still links the item to wowhead."""
    head_bis = bis("head", 123, "Mystery Helm", drop="Dropped somewhere")
    other_items = [item for item in BIS_ITEMS if item.slot != "head"] + [head_bis]
    equipped_items = fill_matching({"head": equipped("head", 124, "Old Helm", 250)})
    _, actions = analyze_gear(equipped_items, other_items, BIS_ILVL)
    action = next(a for a in actions if a.slot == "head")
    segs = segment_map(action.detail_segments)
    assert ("Mystery Helm",
            "https://www.wowhead.com/item=123/mystery-helm") in segs
    assert all(url is None or "wowhead.com" in url for _, url in segs)


def test_catchup_action_has_no_link_segments():
    action = catchup_action(avg_ilvl=277, bis_max_ilvl=289)
    assert action.title == "".join(s.text for s in action.title_segments)
    assert action.detail == "".join(s.text for s in action.detail_segments)
    assert all(
        s.url is None
        for s in action.title_segments + action.detail_segments
    )


# ── Catch-up roadmap by average item level ─────────────────────────────

def test_catchup_fresh_90_roadmap_starts_with_showdown_zones():
    """Freshly-90 / low-ilvl users get manageable steps, not Mythic raid."""
    action = catchup_action(avg_ilvl=245, bis_max_ilvl=289)
    assert "Val" in action.detail and "Naigtal" in action.detail
    assert "field accolades" in action.detail
    assert "Maren Silverwing" in action.detail
    assert "Champion" in action.detail
    assert "World Quests" in action.detail
    assert "Mythic raid" not in action.detail
    # The roadmap must rank high for fresh players, not be truncated.
    assert action.urgency == pytest.approx((289 - 245) * 1.0)


def test_catchup_champion_band_mentions_raid_keys_and_showdowns():
    action = catchup_action(avg_ilvl=258, bis_max_ilvl=289)
    assert "Normal raid" in action.detail
    assert "+2-6" in action.detail
    assert "Val and Naigtal" in action.detail
    assert "Maren Silverwing" in action.detail
    assert "World Quests" not in action.detail


def test_catchup_hero_band_mentions_keys_heroic_raid_and_heroic_world_tier():
    action = catchup_action(avg_ilvl=268, bis_max_ilvl=289)
    assert "+7" in action.detail
    assert "Heroic raid" in action.detail
    assert "Heroic World Tier" in action.detail
    assert "Knocking Off the Top" in action.detail
    assert "Dawncrests" in action.detail


def test_catchup_myth_band_mentions_mythic_raid_and_vault():
    action = catchup_action(avg_ilvl=285, bis_max_ilvl=289)
    assert "Mythic raid" in action.detail
    assert "+10" in action.detail
    assert "Knocking Off the Top" in action.detail
    assert "Dawncrests" in action.detail
    assert "Great Vault" in action.detail


def test_catchup_roadmap_is_staged_for_low_ilvl():
    """Low ilvl gets the full ladder; near-BiS gets only the final stretch."""
    fresh = catchup_action(avg_ilvl=240, bis_max_ilvl=289)
    top = catchup_action(avg_ilvl=287, bis_max_ilvl=289)
    assert "220" in fresh.detail  # Adventurer/Veteran ilvls listed
    assert "Adventurer/Veteran" in fresh.detail
    assert "220" not in top.detail
    assert top.urgency == pytest.approx(2 * 0.25)


# ── Item-level-aware per-slot advice ───────────────────────────────────

def test_low_ilvl_replace_detail_suggests_showdown_path():
    """A 250-ilvl player with a far-behind slot is told to fill it with
    Champion gear from the Showdown zones instead of jumping into
    Mythic-track content."""
    equipped_items = fill_matching(
        {"waist": equipped("waist", 9, "Twisted Twilight Sash", 263)}
    )
    _, actions = analyze_gear(equipped_items, BIS_ITEMS + [WAIST_BIS], BIS_ILVL,
                              avg_ilvl=250)
    action = next(a for a in actions if a.slot == "waist")
    assert "Val and Naigtal" in action.detail
    assert "Champion" in action.detail
    assert "Maren Silverwing" in action.detail


def test_small_gap_slot_gets_no_access_note():
    """Slots only a few ilvls behind don't repeat the Showdown note."""
    equipped_items = fill_matching(
        {"waist": equipped("waist", 9, "Twisted Twilight Sash", 270)}
    )
    _, actions = analyze_gear(equipped_items, BIS_ITEMS + [WAIST_BIS], BIS_ILVL,
                              avg_ilvl=250)
    action = next(a for a in actions if a.slot == "waist")
    assert "Naigtal" not in action.detail


def test_fill_empty_slot_gets_access_note_for_low_ilvl():
    equipped_items = fill_matching({"waist": None})
    _, actions = analyze_gear(equipped_items, BIS_ITEMS + [WAIST_BIS], BIS_ILVL,
                              avg_ilvl=250)
    action = next(a for a in actions if a.slot == "waist")
    assert "Val and Naigtal" in action.detail


def test_high_ilvl_replace_detail_has_no_access_note():
    equipped_items = fill_matching(
        {"waist": equipped("waist", 9, "Twisted Twilight Sash", 263)}
    )
    _, actions = analyze_gear(equipped_items, BIS_ITEMS + [WAIST_BIS], BIS_ILVL,
                              avg_ilvl=280)
    action = next(a for a in actions if a.slot == "waist")
    assert "Naigtal" not in action.detail
    assert "Champion" not in action.detail


def test_mid_ilvl_hero_target_detail_suggests_hero_sources():
    """A Hero-track BiS for a sub-Hero player names the +7/Heroic path."""
    item = bis(
        "hands", 777, "Heroic Gloves", drop="Dropped by Rotmire",
        links=["//www.icy-veins.com/wow/rotmire-raid-guide"],
        link_texts=["Rotmire"], bonus=[13654],
    )
    item.track = "Heroic Raid"
    item.ilvl = 268
    equipped_items = fill_matching(
        {"hands": equipped("hands", 8, "Old Gloves", 240)}
    )
    _, actions = analyze_gear(equipped_items, BIS_ITEMS + [item], BIS_ILVL,
                              avg_ilvl=250)
    action = next(a for a in actions if a.slot == "hands")
    assert "+7 keystones" in action.detail
    assert "Heroic raid" in action.detail
    assert "Naigtal" not in action.detail


def test_dungeon_detail_lists_key_tracks():
    """Dungeon drops: +2-6 Champion, +7 Hero, +10 Great Vault Myth."""
    equipped_items = fill_matching(
        {"legs": equipped("legs", 501, "Old Legs", 260)}
    )
    _, actions = analyze_gear(equipped_items, BIS_ITEMS, BIS_ILVL)
    action = next(a for a in actions if a.slot == "legs")
    assert "Champion-track from +2-6" in action.detail
    assert "Hero-track from +7" in action.detail
    assert "+10 Great Vault" in action.detail


def test_raid_boss_with_mythic_plus_track_omits_difficulty():
    """A raid boss tagged with the M+ bonus track has no bogus difficulty."""
    item = bis(
        "neck", 268291, "Rotmire's Sporeheart", drop="Rotmire",
        links=["//www.icy-veins.com/wow/rotmire-raid-guide"],
        link_texts=["Rotmire"], bonus=[12806],
    )
    item.track = "Mythic+"
    other_items = [b for b in BIS_ITEMS if b.slot != "neck"] + [item]
    equipped_items = fill_matching(
        {"neck": equipped("neck", 8, "Old Neck", 263)}
    )
    _, actions = analyze_gear(equipped_items, other_items, BIS_ILVL)
    action = next(a for a in actions if a.slot == "neck")
    assert "in the current raid to loot" in action.detail
    assert "difficulty" not in action.detail


# ── Upgrade guidance ───────────────────────────────────────────────────

def upgrade_action(item: BisItem) -> Action:
    """Equip the BiS item below target ilvl so the upgrade task fires."""
    equipped_items = fill_matching(
        {item.slot: equipped(item.slot, item.item_id, item.name, 276)}
    )
    _, actions = analyze_gear(equipped_items, BIS_ITEMS + [item], BIS_ILVL)
    return next(a for a in actions if a.slot == item.slot)


def test_upgrade_mythic_plus_guidance_is_concrete():
    """Mythic+ track: name the exact keys and the crest/vault path."""
    item = bis(
        "hands", 777, "Abyssal Immolator's Grasps", drop="Dropped by Vorasius",
        links=["//www.icy-veins.com/wow/vorasius-raid-guide"],
        link_texts=["Vorasius"], bonus=[12806],
    )
    item.track = "Mythic+"
    action = upgrade_action(item)
    assert action.category == "upgrade"
    assert "Mythic+ keystones" in action.detail
    assert "+2-6" in action.detail and "+7" in action.detail and "+10" in action.detail
    assert "Great Vault" in action.detail
    assert "Dawncrests" in action.detail
    assert "Cuzolth" in action.detail
    assert "289" in action.detail


def test_upgrade_mythic_raid_guidance_is_concrete():
    item = bis("hands", 777, "Mythic Raid Gloves", drop="Dropped by Rotmire",
               links=["//www.icy-veins.com/wow/rotmire-raid-guide"],
               link_texts=["Rotmire"], bonus=[13786])
    item.track = "Mythic Raid"
    action = upgrade_action(item)
    assert "Mythic difficulty" in action.detail
    assert "Great Vault" in action.detail
    assert "Dawncrests" in action.detail


def test_upgrade_heroic_raid_guidance_is_concrete():
    item = bis("hands", 777, "Heroic Raid Gloves", drop="Dropped by Rotmire",
               links=["//www.icy-veins.com/wow/rotmire-raid-guide"],
               link_texts=["Rotmire"], bonus=[13654])
    item.track = "Heroic Raid"
    action = upgrade_action(item)
    assert "Heroic difficulty" in action.detail
    assert "Great Vault" in action.detail
    assert "Dawncrests" in action.detail


def test_upgrade_unknown_track_states_both_possibilities():
    item = bis("hands", 777, "Mystery Gloves", drop="Dropped somewhere", bonus=[])
    action = upgrade_action(item)
    assert "Mythic or Hero" in action.detail
    assert "Great Vault" in action.detail
    assert "Dawncrests" in action.detail


def test_upgrade_crafted_guidance_is_concrete():
    item = bis(
        "hands", 777, "Crafted Gloves", drop="Crafted by Tailoring",
        links=["//www.icy-veins.com/wow/professions-making-gold#buying-crafted-gear",
               "//www.icy-veins.com/wow/professions-tailoring"],
        link_texts=["Crafted", "Tailoring"],
    )
    action = upgrade_action(item)
    assert "re-craft" in action.detail or "crafter" in action.detail
    assert "Dawncrests" in action.detail
    assert "289" in action.detail


def test_upgrade_catalyst_guidance_is_concrete():
    item = bis(
        "hands", 777, "Tier Gloves", drop="Catalyst",
        links=["//www.icy-veins.com/wow/catalyst-guide"],
        link_texts=["Catalyst"], bonus=[13786],
    )
    item.track = "Mythic Raid"
    action = upgrade_action(item)
    assert "Catalyst" in action.detail
    assert "Great Vault" in action.detail
    assert "Dawncrests" in action.detail
    assert "Mythic" in action.detail
