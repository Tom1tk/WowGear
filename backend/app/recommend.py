"""Rule-based gear comparison and recommendation engine."""

import re

from .models import Action, BisItem, EquippedItem, SLOT_LABELS, SlotComparison

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
            actions.append(
                Action(
                    slot=slot, category="gear",
                    title=f"Fill empty {SLOT_LABELS[slot].lower()}: get {bis.name} ({bis_ilvl})",
                    detail=_drop_detail(bis, bis_ilvl),
                    urgency=EMPTY_BASE_URGENCY + gap * SLOT_WEIGHTS.get(slot, 1.0),
                    target_item=bis.name, target_ilvl=bis_ilvl,
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
                actions.append(
                    Action(
                        slot=slot, category="upgrade",
                        title=f"Upgrade your {bis.name} ({current.ilvl} -> {bis_ilvl})",
                        detail=(
                            f"You already have the BiS item. Push {_track_hint(bis, bis_ilvl)} "
                            "to get a higher-item-level drop of it."
                        ),
                        urgency=gap * UPGRADE_SAME_ITEM_FACTOR * SLOT_WEIGHTS.get(slot, 1.0),
                        target_item=bis.name, target_ilvl=bis_ilvl,
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
            actions.append(
                Action(
                    slot=slot, category="gear",
                    title=(
                        f"Replace {SLOT_LABELS[slot].lower()}: {current.name} ({current.ilvl}) "
                        f"-> {bis.name} ({bis_ilvl})"
                    ),
                    detail=_drop_detail(bis, bis_ilvl),
                    urgency=gap * SLOT_WEIGHTS.get(slot, 1.0),
                    target_item=bis.name, target_ilvl=bis_ilvl,
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
    )


def _drop_detail(bis: BisItem, bis_ilvl: int) -> str:
    text = bis.drop or ""
    if not text:
        return f"Acquire {bis.name} ({bis_ilvl}) — check the Icy Veins guide for the drop source."

    dungeon = _match_link(bis.drop_links, r"([\w-]+)-dungeon-guide")
    if dungeon:
        return (
            f"Farm {_link_text(bis, dungeon)} on Mythic+ (Hero-track drops) until "
            f"{bis.name} ({bis_ilvl}) drops."
        )
    boss = _match_link(bis.drop_links, r"([\w-]+)-raid-guide")
    if boss:
        return (
            f"Kill {_link_text(bis, boss)} in the current raid on "
            f"{_difficulty_phrase(bis.track)} to loot {bis.name} ({bis_ilvl})."
        )
    if _match_link(bis.drop_links, r"catalyst-guide"):
        return (
            f"Convert a tier token at the Catalyst (see the Catalyst guide) — "
            f"you need {bis.name} ({bis_ilvl})."
        )
    profession = _match_link(bis.drop_links, r"professions-([\w-]+)")
    if profession:
        return (
            f"Craft {bis.name} ({bis_ilvl}) with {_title(profession)} — "
            "or buy it on the Auction House."
        )
    return f"Acquire {bis.name} ({bis_ilvl}) — {text}."


def _match_link(links: list[str], pattern: str) -> str | None:
    for link in links:
        match = re.search(pattern, link)
        if match:
            return match.group(1)
    return None


def _link_text(bis: BisItem, slug: str) -> str:
    """Prefer the page's own link text (keeps punctuation like Belo'ren),
    falling back to the slug title-cased."""
    for link, text in zip(bis.drop_links, bis.drop_link_texts):
        if slug in link and text:
            return text
    return _title(slug)


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
