"""Compare the computed gear lists with human-made reference lists.

Writes reports/validation.md. For each reference item the report says:
  top      - in our top list for that slot (level 60 pre-raid, or the level range)
  close    - not in our top list, but scores at least 90% of our #1 (a close call)
  ranked   - we know it and it is usable, but other items score higher
  unusable - our class rules say the class cannot use it (the guide may be wrong)
  missing  - the item is not in our data, or has no source we accept

    python scripts/data/validate.py
"""

from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from _common import ERA, REPORTS, ROOT, read_json  # noqa: E402
from build_gear import Builder  # noqa: E402

SLOT_MAP = {"head": "head", "neck": "neck", "shoulder": "shoulders", "back": "back", "chest": "chest",
            "wrist": "wrist", "hands": "hands", "waist": "waist", "legs": "legs", "feet": "feet",
            "finger": "ring", "trinket": "trinket"}


def slot_for(label: str) -> str | None:
    """Reference slot label -> our slot; None = search all weapon slots."""
    base = label.replace("_", " ").split(" ")[0]
    if base in SLOT_MAP:
        return SLOT_MAP[base]
    if any(w in label for w in ("ranged", "wand", "bow", "gun", "crossbow", "thrown")):
        return "ranged"
    if any(w in label for w in ("relic", "idol", "totem", "libram")):
        return "relic"
    return None


WEAPON_SLOTS = ("main_hand", "off_hand", "two_hand", "ranged")


def gear_file(key: str, builder: Builder):
    cls_slug = key.split(".")[0]
    cls_id = next(k for k, v in builder.classes.items() if v["slug"] == cls_slug)
    factions = sorted({r["faction"] for r in builder.races.values() if int(cls_id) in r["classes"]})
    faction = "H" if "H" in factions and cls_slug == "shaman" else factions[0]
    return cls_id, faction, read_json(ROOT / "frontend" / "data" / "gear" / f"{key}.{faction}.json")


def classify(name, slot, gear, builder, cls_id, levels=None):
    ids = [iid for iid, it in builder.items.items() if it["name"].lower() == name.lower()]
    if not ids:
        return "missing", "not in item data"
    if all(builder.usable_from(builder.items[i], cls_id) is None for i in ids):
        return "unusable", "class cannot equip it"
    slots = [slot] if slot else [s for s in WEAPON_SLOTS if s in gear["slots"]]
    lo, hi = levels or (60, 60)
    best_rank = None
    for sl in slots:
        pts = [p for p in gear["slots"].get(sl, []) if p["tier"] == 0]
        # points in effect during [lo, hi]: the last one at or before lo, plus later ones <= hi
        active = [p for p in pts if lo < p["level"] <= hi]
        before = [p for p in pts if p["level"] <= lo]
        if before:
            active.append(before[-1])
        for pt in active:
            for rank, (iid, _score) in enumerate(pt["items"]):
                if iid in ids:
                    best_rank = rank if best_rank is None else min(best_rank, rank)
    if best_rank is not None:
        return "top", f"our #{best_rank + 1}"
    # How close is it? Score the reference item and compare with our #1.
    key = f"{builder.classes[cls_id]['slug']}.{gear['spec']}"
    prof = builder.profiles[builder.aliases.get(key, key)]
    wkey = "endgame" if levels is None or levels[1] >= 60 else "leveling"
    best_ref = max((builder.score(builder.items[i], i, prof[wkey], prof.get("weapon", {}),
                                  builder.slot_of(builder.items[i], None) or "", None, cls_id) for i in ids), default=0)
    ours = 0
    for sl in slots:
        pts = [p for p in gear["slots"].get(sl, []) if p["tier"] == 0 and p["level"] <= hi]
        if pts and pts[-1]["items"]:
            ours = max(ours, pts[-1]["items"][0][1])
    if ours and best_ref >= 0.9 * ours:
        return "close", f"scores {best_ref:.0f} vs our #1 {ours:.0f}"
    if not any(i in gear["items"] or i in builder.sources for i in ids):
        return "missing", "no accepted source"
    return "ranked", "usable, other items score higher"


def main():
    b = Builder()
    ref = read_json(ERA / "reference" / "wowtbc_preraid.json")["lists"]
    lines = ["# Validation against human-made lists", "",
             "Reference: wowtbc.gg Classic pre-raid lists (level 60, tier 0) and the NoobToBoss",
             "feral druid leveling guide. `top` = in our top 3 for that slot (top 4 for rings and",
             "trinkets). `unusable` means our class rules say the class cannot equip the item",
             "(then the guide is wrong, or our rules are).", "",
             "`close` = scores at least 90% of our #1 (a close call, not a disagreement).", "",
             "| Spec | Items | top | close | ranked | unusable | missing | top+close |", "|---|---|---|---|---|---|---|---|"]
    details = []
    total = Counter()
    for key, lst in sorted(ref.items()):
        cls_id, faction, gear = gear_file(key, b)
        counts = Counter()
        rows = []
        for row in lst["items"]:
            slot = slot_for(row["slot"])
            status, note = classify(row["item"], slot, gear, b, cls_id)
            counts[status] += 1
            rows.append(f"| {row['slot']} | {row['item']} | {status} | {note} |")
        n = sum(counts.values())
        agree = (counts["top"] + counts["close"]) / max(1, n - counts["unusable"])
        total.update(counts)
        lines.append(f"| {key} ({faction}) | {n} | {counts['top']} | {counts['close']} | {counts['ranked']} | "
                     f"{counts['unusable']} | {counts['missing']} | {agree:.0%} |")
        details += [f"### {key} — [{lst['url']}]({lst['url']})", "", "| Slot | Item | Result | Note |",
                    "|---|---|---|---|", *rows, ""]
    n = sum(total.values())
    usable = max(1, n - total["unusable"])
    lines += ["", f"**Overall:** {total['top']} of {usable} usable reference items are in our top lists "
              f"({total['top'] / usable:.0%}); with close calls {total['top'] + total['close']} "
              f"({(total['top'] + total['close']) / usable:.0%}).", ""]
    lev = read_json(ERA / "reference" / "noobtoboss_druid_leveling.json")
    cls_id, faction, gear = gear_file(lev["spec"], b)
    lines += ["## Leveling: NoobToBoss feral druid guide", "", "| Item | Levels | Result | Note |", "|---|---|---|---|"]
    for row in lev["items"]:
        status, note = classify(row["item"], None, gear, b, cls_id, tuple(row["levels"]))
        lines.append(f"| {row['item']} | {row['levels'][0]}-{row['levels'][1]} | {status} | {note} |")
    lines += ["", "## Details (pre-raid)", "", *details]
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:40]))


if __name__ == "__main__":
    main()
