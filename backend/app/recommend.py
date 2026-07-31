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
CATCHUP_FACTOR = 0.25
UPGRADE_SAME_ITEM_FACTOR = 0.8


def analyze_gear(
    equipped: dict[str, EquippedItem],
    bis_items: list[BisItem],
    bis_max_ilvl: int,
) -> tuple[list[SlotComparison], list[Action]]:
    """Compare equipped gear against BiS items; return per-slot comparisons and
    unsorted/rankless actions (rank/limit applied by the caller)."""
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
            detail_segments = _drop_segments(bis, bis_ilvl)
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
                detail = (
                    f"You already have the BiS item. Push {_track_hint(bis, bis_ilvl)} "
                    "to get a higher-item-level drop of it."
                )
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
            detail_segments = _drop_segments(bis, bis_ilvl)
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

    Advice is tiered by the size of the deficit: within 1 ilvl of the ceiling
    there is nothing worth doing, so no action is emitted (telling a 288
    player to farm Heroic dungeons for one point is bad advice)."""
    if avg_ilvl is None or bis_max_ilvl <= 0 or avg_ilvl >= bis_max_ilvl:
        return None
    deficit = bis_max_ilvl - avg_ilvl
    if deficit < 2:
        return None

    if deficit <= 4:
        detail = (
            f"Your average item level is {avg_ilvl}; the BiS list targets {bis_max_ilvl}. "
            "You're nearly there — pick up Hero-track pieces from Mythic+ keys and the "
            "Great Vault, then spend Dawncrests at the upgrade vendor (Cuzolth in "
            "Silvermoon City) to push your best items up their track. Ascendant Voidcores "
            "can add bonus ranks to Hero/Myth-track weapons and trinkets."
        )
    elif deficit <= 9:
        detail = (
            f"Your average item level is {avg_ilvl}; the BiS list targets {bis_max_ilvl}. "
            "Run Mythic+ keystones (Hero-track drops from +6 keys, Myth-track from +10) "
            "and Heroic raid, and open the Great Vault every week. Upgrade your keepers "
            "with Dawncrests at Cuzolth in Silvermoon City, and use Nebulous Voidcores "
            "(2 per week) for extra Hero/Myth-track rolls."
        )
    else:
        detail = (
            f"Your average item level is {avg_ilvl}; the BiS list targets {bis_max_ilvl}. "
            "Start with Delves and Heroic dungeons (Veteran/Champion-track gear), then move "
            "to Mythic+ keystones for Hero-track drops and the Great Vault each week. "
            "Dawncrests upgrade gear along its track at Cuzolth in Silvermoon City."
        )
    return Action(
        category="catchup",
        title=f"Close the item level gap ({avg_ilvl} -> {bis_max_ilvl})",
        detail=detail,
        urgency=deficit * CATCHUP_FACTOR,
        target_ilvl=bis_max_ilvl,
        title_segments=[_seg(f"Close the item level gap ({avg_ilvl} -> {bis_max_ilvl})")],
        detail_segments=[_seg(detail)],
    )


def _drop_segments(bis: BisItem, bis_ilvl: int) -> list[TextSegment]:
    """Drop advice as linked text; concatenating the segments yields exactly
    the plain `detail` string. Item names link to Wowhead; bosses, dungeons,
    the Catalyst and professions link to their Icy Veins guides (from the
    parsed BiS page, so a new season's sources flow through automatically)."""
    text = bis.drop or ""
    if not text:
        return [
            _seg("Acquire "), _item_seg(bis),
            _seg(f" ({bis_ilvl}) — check the Icy Veins guide for the drop source."),
        ]

    dungeon = _drop_link(bis, r"([\w-]+)-dungeon-guide")
    if dungeon:
        return [
            _seg("Farm "), _seg(dungeon[0], dungeon[1]),
            _seg(" on Mythic+ (Hero-track drops) until "),
            _item_seg(bis), _seg(f" ({bis_ilvl}) drops."),
        ]
    boss = _drop_link(bis, r"([\w-]+)-raid-guide")
    if boss:
        return [
            _seg("Kill "), _seg(boss[0], boss[1]),
            _seg(f" in the current raid on {_difficulty_phrase(bis.track)} to loot "),
            _item_seg(bis), _seg(f" ({bis_ilvl})."),
        ]
    catalyst = _drop_link(bis, r"catalyst-guide")
    if catalyst:
        return [
            _seg("Convert a tier token at the Catalyst (see the "),
            _seg("Catalyst guide", catalyst[1]),
            _seg(") — you need "),
            _item_seg(bis), _seg(f" ({bis_ilvl})."),
        ]
    profession = _drop_link(bis, r"professions-([\w-]+)")
    if profession:
        return [
            _seg("Craft "), _item_seg(bis),
            _seg(f" ({bis_ilvl}) with "),
            _seg(profession[0], profession[1]),
            _seg(" — or buy it on the Auction House."),
        ]
    return [
        _seg("Acquire "), _item_seg(bis),
        _seg(f" ({bis_ilvl}) — {text}."),
    ]


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


def _difficulty_phrase(track: str | None) -> str:
    return {
        "Mythic Raid": "Mythic difficulty",
        "Heroic Raid": "Heroic difficulty",
        "Mythic+": "the Mythic+ track",
    }.get(track, "the current difficulty")


def _title(slug: str) -> str:
    words = slug.replace("-", " ").split()
    small = {"of", "the", "and", "in", "on", "at", "to", "for"}
    return " ".join(
        word.capitalize() if index == 0 or word.lower() not in small else word.lower()
        for index, word in enumerate(words)
    )


def _track_hint(bis: BisItem, bis_ilvl: int) -> str:
    if bis.track:
        return f"the {bis.track.lower()} track"
    return f"difficulties that drop ilvl {bis_ilvl} gear"
