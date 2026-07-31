"""Rule-based gear comparison and recommendation engine."""

import re

from .models import Action, BisItem, EquippedItem, SLOT_LABELS, SlotComparison, TextSegment

SLOT_WEIGHTS = {
    "main_hand": 1.5,
    "trinket_1": 1.4,
    "trinket_2": 1.4,
    "chest": 1.2,
    "legs": 1.2,
    "head": 1.1,
}
EMPTY_BASE_URGENCY = 30.0
UPGRADE_SAME_ITEM_FACTOR = 0.8


def analyze_gear(
    equipped: dict[str, EquippedItem],
    bis_items: list[BisItem],
    bis_max_ilvl: int,
    avg_ilvl: int | None = None,
) -> tuple[list[SlotComparison], list[Action]]:
    """Compare equipped gear against BiS items; return per-slot comparisons and
    unsorted/rankless actions (rank/limit applied by the caller).

    `avg_ilvl` personalises the drop advice: players far below the track
    their BiS target lives on get a manageable stepping-stone note (e.g.
    Showdown-zone Champion gear) instead of a straight Mythic-track order."""
    bis_by_slot: dict[str, BisItem] = {}
    for bis in bis_items:
        bis_by_slot.setdefault(bis.slot, bis)

    comparisons: list[SlotComparison] = []
    actions: list[Action] = []

    # A two-handed main hand weapon means the off-hand slot cannot be filled
    # (e.g. a Brewmaster with a staff); never recommend one in that case.
    main_hand = equipped.get("main_hand")
    main_is_two_handed = bool(
        main_hand
        and main_hand.inventory_type in ("TWOHWEAPON", "TWO_HANDED", "TWO-HANDED")
    )

    for slot in SLOT_LABELS:
        if slot == "off_hand" and main_is_two_handed:
            comparisons.append(
                SlotComparison(
                    slot=slot, slot_label=SLOT_LABELS[slot], equipped=equipped.get(slot),
                    bis=None, status="no_bis", ilvl_gap=None,
                )
            )
            continue
        bis = bis_by_slot.get(slot)
        current = equipped.get(slot)
        if bis is None:
            comparisons.append(
                SlotComparison(
                    slot=slot, slot_label=SLOT_LABELS[slot], equipped=current,
                    bis=None, status="no_bis", ilvl_gap=None,
                )
            )
            continue

        bis_ilvl = bis.ilvl or bis_max_ilvl or 0

        if current is None:
            gap = bis_ilvl
            comparisons.append(
                SlotComparison(
                    slot=slot, slot_label=SLOT_LABELS[slot], equipped=None, bis=bis,
                    status="empty", ilvl_gap=gap,
                )
            )
            title_segments = [
                _seg(f"Fill empty {SLOT_LABELS[slot].lower()}: get "),
                _item_seg(bis),
                _seg(f" ({bis_ilvl})"),
            ]
            detail_segments = _drop_segments(bis, bis_ilvl, avg_ilvl, gap)
            actions.append(
                Action(
                    slot=slot, category="gear",
                    title=_plain(title_segments),
                    detail=_plain(detail_segments),
                    urgency=EMPTY_BASE_URGENCY + gap * SLOT_WEIGHTS.get(slot, 1.0),
                    target_item=bis.name, target_ilvl=bis_ilvl,
                    title_segments=title_segments,
                    detail_segments=detail_segments,
                )
            )
        elif current.item_id == bis.item_id:
            if current.ilvl < bis_ilvl:
                gap = bis_ilvl - current.ilvl
                comparisons.append(
                    SlotComparison(
                        slot=slot, slot_label=SLOT_LABELS[slot], equipped=current,
                        bis=bis, status="upgrade", ilvl_gap=gap,
                    )
                )
                title_segments = [
                    _seg("Upgrade your "),
                    _item_seg(bis),
                    _seg(f" ({current.ilvl} -> {bis_ilvl})"),
                ]
                detail = _upgrade_guidance(bis, bis_ilvl)
                actions.append(
                    Action(
                        slot=slot, category="upgrade",
                        title=_plain(title_segments),
                        detail=detail,
                        urgency=gap * UPGRADE_SAME_ITEM_FACTOR * SLOT_WEIGHTS.get(slot, 1.0),
                        target_item=bis.name, target_ilvl=bis_ilvl,
                        title_segments=title_segments,
                        detail_segments=[_seg(detail)],
                    )
                )
            else:
                comparisons.append(
                    SlotComparison(
                        slot=slot, slot_label=SLOT_LABELS[slot], equipped=current,
                        bis=bis, status="match", ilvl_gap=0,
                    )
                )
        else:
            gap = max(0, bis_ilvl - current.ilvl)
            if gap <= 0:
                comparisons.append(
                    SlotComparison(
                        slot=slot, slot_label=SLOT_LABELS[slot], equipped=current,
                        bis=bis, status="ahead", ilvl_gap=0,
                    )
                )
                continue
            comparisons.append(
                SlotComparison(
                    slot=slot, slot_label=SLOT_LABELS[slot], equipped=current,
                    bis=bis, status="upgrade", ilvl_gap=gap,
                )
            )
            title_segments = [
                _seg(f"Replace {SLOT_LABELS[slot].lower()}: "),
                _item_seg_id(current.item_id, current.name),
                _seg(f" ({current.ilvl}) -> "),
                _item_seg(bis),
                _seg(f" ({bis_ilvl})"),
            ]
            detail_segments = _drop_segments(bis, bis_ilvl, avg_ilvl, gap)
            actions.append(
                Action(
                    slot=slot, category="gear",
                    title=_plain(title_segments),
                    detail=_plain(detail_segments),
                    urgency=gap * SLOT_WEIGHTS.get(slot, 1.0),
                    target_item=bis.name, target_ilvl=bis_ilvl,
                    title_segments=title_segments,
                    detail_segments=detail_segments,
                )
            )

    actions.sort(key=lambda action: action.urgency, reverse=True)
    return comparisons, actions


def catchup_action(avg_ilvl: int | None, bis_max_ilvl: int) -> Action | None:
    """Generic ilvl catch-up action when the character lags the BiS ceiling.

    Advice is a roadmap tiered by the player's average item level, so a
    freshly-90 character gets the manageable open-world path (Showdown
    zones, field accolades, Heroic dungeons) before group content, while a
    near-BiS player gets only the final Myth-track stretch. Within 1 ilvl
    of the ceiling there is nothing worth doing, so no action is emitted
    (telling a 288 player to farm Heroic dungeons for one point is bad
    advice)."""
    if avg_ilvl is None or bis_max_ilvl <= 0 or avg_ilvl >= bis_max_ilvl:
        return None
    deficit = bis_max_ilvl - avg_ilvl
    if deficit < 2:
        return None

    detail, factor = _catchup_detail(avg_ilvl, bis_max_ilvl)
    return Action(
        category="catchup",
        title=f"Close the item level gap ({avg_ilvl} -> {bis_max_ilvl})",
        detail=detail,
        urgency=deficit * factor,
        target_ilvl=bis_max_ilvl,
        title_segments=[_seg(f"Close the item level gap ({avg_ilvl} -> {bis_max_ilvl})")],
        detail_segments=[_seg(detail)],
    )


def _catchup_detail(avg_ilvl: int, bis_max_ilvl: int) -> tuple[str, float]:
    for threshold, factor, template in CATCHUP_BANDS:
        if avg_ilvl < threshold:
            return template.format(avg=avg_ilvl, max=bis_max_ilvl), factor
    return CATCHUP_MYTH_COPY.format(avg=avg_ilvl, max=bis_max_ilvl), CATCHUP_MYTH_FACTOR


def _drop_segments(
    bis: BisItem, bis_ilvl: int, avg_ilvl: int | None = None, gap: int = 0
) -> list[TextSegment]:
    """Drop advice as linked text; concatenating the segments yields exactly
    the plain `detail` string. Item names link to Wowhead; bosses, dungeons,
    the Catalyst and professions link to their Icy Veins guides (from the
    parsed BiS page, so a new season's sources flow through automatically).
    When the player's average ilvl is below the target track, an access note
    names the stepping-stone path."""
    text = bis.drop or ""
    if not text:
        return [
            _seg("Acquire "), _item_seg(bis),
            _seg(f" ({bis_ilvl}) — check the Icy Veins guide for the drop source."),
        ]

    dungeon = _drop_link(bis, r"([\w-]+)-dungeon-guide")
    if dungeon:
        segments = [
            _seg("Farm "), _seg(dungeon[0], dungeon[1]),
            _seg(" on Mythic+ keys — Champion-track from +2-6, Hero-track from +7, "
                 "Myth-track from the +10 Great Vault — until "),
            _item_seg(bis), _seg(f" ({bis_ilvl}) drops."),
        ]
    else:
        boss = _drop_link(bis, r"([\w-]+)-raid-guide")
        if boss:
            phrase = _difficulty_phrase(bis.track)
            difficulty = f" on {phrase}" if phrase else ""
            segments = [
                _seg("Kill "), _seg(boss[0], boss[1]),
                _seg(f" in the current raid{difficulty} to loot "),
                _item_seg(bis), _seg(f" ({bis_ilvl})."),
            ]
        else:
            catalyst = _drop_link(bis, r"catalyst-guide")
            if catalyst:
                segments = [
                    _seg("Convert a tier token at the Catalyst (see the "),
                    _seg("Catalyst guide", catalyst[1]),
                    _seg(") — you need "),
                    _item_seg(bis), _seg(f" ({bis_ilvl})."),
                ]
            else:
                profession = _drop_link(bis, r"professions-([\w-]+)")
                if profession:
                    segments = [
                        _seg("Craft "), _item_seg(bis),
                        _seg(f" ({bis_ilvl}) with "),
                        _seg(profession[0], profession[1]),
                        _seg(" — or buy it on the Auction House."),
                    ]
                else:
                    segments = [
                        _seg("Acquire "), _item_seg(bis),
                        _seg(f" ({bis_ilvl}) — {text}."),
                    ]
    note = _access_note(bis, bis_ilvl, avg_ilvl, gap)
    if note:
        segments.append(_seg(note))
    return segments


def _access_note(
    bis: BisItem, bis_ilvl: int, avg_ilvl: int | None, gap: int
) -> str:
    """Stepping-stone note for players below the track their target sits on,
    only when the slot itself is far behind (gap >= ACCESS_GAP_THRESHOLD):
    Myth-track targets point at the Showdown-zone Champion path; Hero-track
    targets name +7/Heroic sources."""
    if not avg_ilvl or avg_ilvl >= 272 or gap < ACCESS_GAP_THRESHOLD:
        return ""
    if bis_ilvl >= 272 or bis.track in ("Mythic Raid", "Mythic+"):
        return MYTH_GAP_NOTE
    if avg_ilvl < 259 and (bis_ilvl >= 259 or bis.track == "Heroic Raid"):
        return HERO_GAP_NOTE.format(avg=avg_ilvl)
    return ""


def _drop_link(bis: BisItem, pattern: str) -> tuple[str, str] | None:
    """First drop link matching `pattern`: its link text (page text when
    present, else the slug title-cased) and href. The making-gold link on
    crafted items is a money guide, not a profession — skip it."""
    for index, link in enumerate(bis.drop_links):
        match = re.search(pattern, link)
        if not match:
            continue
        slug = match.group(1) if match.re.groups else match.group(0)
        if slug == "making-gold":
            continue
        text = bis.drop_link_texts[index] if index < len(bis.drop_link_texts) else ""
        return (text or _title(slug)), link
    return None


def _item_seg(bis: BisItem) -> TextSegment:
    return _seg(bis.name, _wowhead_url(bis.item_id, bis.name, bis.bonus))


def _item_seg_id(item_id: int, name: str) -> TextSegment:
    return _seg(name, _wowhead_url(item_id, name))


def _wowhead_url(item_id: int, name: str, bonus: list[int] | None = None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    url = f"https://www.wowhead.com/item={item_id}/{slug}"
    if bonus:
        url += "?bonus=" + ":".join(str(b) for b in bonus)
    return url


def _seg(text: str, url: str | None = None) -> TextSegment:
    return TextSegment(text=text, url=url)


def _plain(segments: list[TextSegment]) -> str:
    return "".join(s.text for s in segments)


def _difficulty_phrase(track: str | None) -> str | None:
    """Difficulty phrase for raid drops. The M+ track says nothing about raid
    difficulty, so a boss tagged with a Mythic+ bonus id gets no phrase."""
    return {
        "Mythic Raid": "Mythic difficulty",
        "Heroic Raid": "Heroic difficulty",
    }.get(track) if track else None


def _title(slug: str) -> str:
    words = slug.replace("-", " ").split()
    small = {"of", "the", "and", "in", "on", "at", "to", "for"}
    return " ".join(
        word.capitalize() if index == 0 or word.lower() not in small else word.lower()
        for index, word in enumerate(words)
    )


# Season config: personalised upgrade advice per track. A new season's
# numbers (key thresholds, crests, vendor) live here in one place — the
# track labels must match BONUS_TRACKS in icyveins.py.
UPGRADE_GUIDANCE = {
    "Mythic+": (
        "You already have the BiS item. Run Mythic+ keystones: the same item drops "
        "on the Champion track from +2-6 keys, on the Hero track from +7 keys, and "
        "the Myth track comes from the weekly Great Vault's Mythic slot on a +10 key. "
        "If your copy is already on the Myth track, spend Dawncrests at Cuzolth in "
        "Silvermoon City to upgrade it to {bis_ilvl}; crests can't lift a lower "
        "track across tiers."
    ),
    "Mythic Raid": (
        "You already have the BiS item. Kill bosses in the current raid on Mythic "
        "difficulty — the item drops there at up to {bis_ilvl} — and the weekly "
        "Great Vault's Mythic slot can roll it as well. If your copy is already "
        "Myth-track, spend Dawncrests at Cuzolth in Silvermoon City to upgrade it "
        "to {bis_ilvl}; a lower-track copy needs a Mythic-difficulty or +10 keystone drop."
    ),
    "Heroic Raid": (
        "You already have the BiS item. Kill bosses in the current raid on Heroic "
        "difficulty — the item drops there at up to {bis_ilvl} — and the weekly "
        "Great Vault's Heroic slot can roll it too. If your copy is already "
        "Hero-track, spend Dawncrests at Cuzolth in Silvermoon City to upgrade it "
        "to {bis_ilvl}; a lower-track copy needs a Heroic-difficulty or +7 keystone drop."
    ),
}

UNKNOWN_TRACK_GUIDANCE = (
    "You already have the BiS item. Push Mythic or Hero content: Mythic difficulty "
    "in the current raid and Mythic+ keys at +10 (Hero track from +7) drop "
    "higher-item-level copies, and the weekly Great Vault can roll one too. If your "
    "copy is on the right track, spend Dawncrests at Cuzolth in Silvermoon City to "
    "upgrade it to {bis_ilvl}."
)

CRAFTED_UPGRADE_GUIDANCE = (
    "You already have the BiS item. Crafted gear reaches {bis_ilvl} by re-crafting "
    "at a higher tier with a crafter, or by spending Dawncrests at Cuzolth in "
    "Silvermoon City to upgrade a Myth-track crafted copy — Myth-track crests come "
    "from the +10 Great Vault and Mythic raid."
)

CATALYST_UPGRADE_GUIDANCE = (
    "You already have the BiS item. Tier gear converts through the Catalyst: get a "
    "higher-item-level copy of the same slot (Mythic raid, +10 keystones, or the "
    "weekly Great Vault's Mythic slot) and convert it. If your copy is already "
    "Myth-track, spend Dawncrests at Cuzolth in Silvermoon City to upgrade it to "
    "{bis_ilvl}."
)

# Season config: catch-up roadmap per average item level band (Midnight S1
# track ladder: Adventurer 220-237, Veteran 233-250, Champion 246-263,
# Hero 259-276, Myth 272-289). Low-ilvl players get the manageable
# open-world path (Val/Naigtal Showdown zones + field accolades) before
# group content; near-BiS players get only the final stretch. The factor
# scales the catch-up urgency so the roadmap ranks high for fresh players.
CATCHUP_BANDS = [
    (254, 1.0, (
        "Your average item level is {avg}; the BiS list targets {max}. Start with "
        "World Quests in Quel'Thalas, Heroic dungeons and Delves for "
        "Adventurer/Veteran gear (220-250). Next, work the Val and Naigtal Showdown "
        "zones on Normal World Tier (portal behind the Field Accolade quartermasters "
        "in Silvermoon City): rares drop Champion gear (246-263) once a day, the "
        "weekly world bosses Imperator Pertinax and Nexus-Captain Leth'ir guarantee a "
        "Champion drop, and field accolades buy Champion gear for any slot from "
        "Maren Silverwing in Silvermoon. From there, Normal raid and Mythic+ keys "
        "+2-6 keep you on the Champion track until you're ready for +7 keystones (Hero)."
    )),
    (264, 0.75, (
        "Your average item level is {avg}; the BiS list targets {max}. Max out the "
        "Champion track (246-263): Normal raid once a week, Mythic+ keys +2-6, "
        "Bountiful Delves tier 7+ with Restored Coffer Keys, and Nightmare Prey "
        "Hunts. Field accolades from the Val and Naigtal Showdown zones buy Champion "
        "gear for any slot (Maren Silverwing in Silvermoon). At ~263, switch to +7 "
        "keystones and Heroic raid for Hero-track gear (259-276)."
    )),
    (277, 0.5, (
        "Your average item level is {avg}; the BiS list targets {max}. Fill out the "
        "Hero track (259-276): Mythic+ keys +7 and higher, Heroic raid once a week, "
        "and Delve Hidden Troves (Trovehunter's Bounty). In the Showdown zones, "
        "Heroic World Tier (recommended ~274) drops Hero gear from the world bosses "
        "and yields far more field accolades for Hero tokens. Myth-track (272-289) "
        "comes from Mythic raid, the Great Vault on a +10 key, and the 'Knocking Off "
        "the Top' quest. Spend Dawncrests at Cuzolth in Silvermoon City to upgrade "
        "gear along its track."
    )),
]
CATCHUP_MYTH_FACTOR = 0.25
CATCHUP_MYTH_COPY = (
    "Your average item level is {avg}; the BiS list targets {max}. Close out the "
    "last stretch: Mythic raid once a week, the Great Vault on a +10 key, and the "
    "Showdown quest 'Knocking Off the Top' (Heroic World Tier) for Myth "
    "cloak/belt/bracers. Crafted gear reaches Myth with 80 Myth Dawncrests. Spend "
    "Dawncrests at Cuzolth in Silvermoon City to push pieces to the top of their "
    "track, and use Ascendant Voidcores on fully-upgraded weapons and trinkets."
)

# Per-slot note for players below the track their BiS target lives on,
# only shown when the slot itself is far behind (large ilvl gap).
MYTH_GAP_NOTE = (
    " You're not geared for Myth-track yet — for now, fill this slot with "
    "Champion gear from the Val and Naigtal Showdown zones (rares, world bosses, "
    "or field accolades at Maren Silverwing in Silvermoon)."
)

HERO_GAP_NOTE = (
    " At {avg} ilvl the Hero-track version comes from +7 keystones or Heroic raid "
    "— or buy it with field accolades from the Showdown zones' Heroic World Tier "
    "(recommended ~274)."
)

ACCESS_GAP_THRESHOLD = 25


def _upgrade_guidance(bis: BisItem, bis_ilvl: int) -> str:
    """What the user should DO to lift an already-owned BiS item to target ilvl:
    the exact content/difficulty/keys per track, and the crest upgrade path.
    Falls back to naming both possibilities when the track is unknown."""
    catalyst = _drop_link(bis, r"catalyst-guide")
    if catalyst:
        return CATALYST_UPGRADE_GUIDANCE.format(bis_ilvl=bis_ilvl)
    if _drop_link(bis, r"professions-([\w-]+)"):
        return CRAFTED_UPGRADE_GUIDANCE.format(bis_ilvl=bis_ilvl)
    template = UPGRADE_GUIDANCE.get(bis.track or "")
    if template:
        return template.format(bis_ilvl=bis_ilvl)
    return UNKNOWN_TRACK_GUIDANCE.format(bis_ilvl=bis_ilvl)
