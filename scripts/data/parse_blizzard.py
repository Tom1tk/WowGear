"""Normalize cached Blizzard Era item JSON into data/era/staging/blizzard.json.

Primary stats come straight from the API. "Equip:" effects are text in the
API (e.g. "Equip: +20 Attack Power."), so they are read with the patterns in
EFFECT_PATTERNS. Effects that no pattern knows (procs, "Use:" effects) are
kept as text and flagged, so the site can show them.

    python scripts/data/parse_blizzard.py
"""

from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import RAW, STAGING, write_json  # noqa: E402

STAT_KEYS = {
    "STRENGTH": "str", "AGILITY": "agi", "STAMINA": "sta", "INTELLECT": "int",
    "SPIRIT": "spi", "ATTACK_POWER": "ap",
    "FIRE_RESISTANCE": "res_fire", "NATURE_RESISTANCE": "res_nature",
    "FROST_RESISTANCE": "res_frost", "SHADOW_RESISTANCE": "res_shadow",
    "ARCANE_RESISTANCE": "res_arcane",
}

N = r"(\d+(?:\.\d+)?)"
EFFECT_PATTERNS = [
    (rf"^Increases damage and healing done by magical spells and effects by up to {N}\.?$", "sp"),
    (rf"^Increases healing done by spells and effects by up to {N}\.?$", "heal"),
    (rf"^Improves your chance to get a critical strike with spells by {N}%\.?$", "spell_crit"),
    (rf"^Improves your chance to get a critical strike by {N}%\.?$", "crit"),
    (rf"^Improves your chance to hit with spells by {N}%\.?$", "spell_hit"),
    (rf"^Improves your chance to hit by {N}%\.?$", "hit"),
    (rf"^Restores {N} mana per 5 sec\.?$", "mp5"),
    (rf"^Restores {N} health per 5 sec\.?$", "hp5"),
    (rf"^\+{N} Attack Power\.?$", "ap"),
    (rf"^\+{N} ranged Attack Power\.?$", "rap"),
    (rf"^\+{N} Attack Power in Cat, Bear, and Dire Bear forms only\.?$", "feral_ap"),
    (rf"^Increased Defense \+{N}\.?$", "def"),
    (rf"^Increases your chance to dodge an attack by {N}%\.?$", "dodge"),
    (rf"^Increases your chance to parry an attack by {N}%\.?$", "parry"),
    (rf"^Increases your chance to block attacks with a shield by {N}%\.?$", "block"),
    (rf"^Increases the block value of your shield by {N}\.?$", "block_value"),
    (rf"^Decreases the magical resistances of your spell targets by {N}\.?$", "spell_pen"),
    (rf"^Increases damage done by Shadow spells and effects by up to {N}\.?$", "sp_shadow"),
    (rf"^Increases damage done by Fire spells and effects by up to {N}\.?$", "sp_fire"),
    (rf"^Increases damage done by Frost spells and effects by up to {N}\.?$", "sp_frost"),
    (rf"^Increases damage done by Nature spells and effects by up to {N}\.?$", "sp_nature"),
    (rf"^Increases damage done by Arcane spells and effects by up to {N}\.?$", "sp_arcane"),
    (rf"^Increases damage done by Holy spells and effects by up to {N}\.?$", "sp_holy"),
    (rf"^\+{N} (Fire|Nature|Frost|Shadow|Arcane) Resistance\.?$", "res"),
    (rf"^\+{N} All Resistances\.?$", "res_all"),
    (rf"^Increased (Daggers|Swords|Maces|Axes|Bows|Guns|Crossbows|Two-handed Swords|"
     rf"Two-handed Maces|Two-handed Axes|Staves|Polearms|Fist Weapons|Unarmed) \+{N}\.?$", "wskill"),
]
COMPILED = [(re.compile(p, re.I), k) for p, k in EFFECT_PATTERNS]


def parse_effect(text: str):
    """Return (stat_key, value) pairs for one effect line, or None."""
    body = re.sub(r"^Equip:\s*", "", text.strip())
    if body == text.strip():
        return None  # "Use:" / "Chance on hit:" — not a passive stat
    for rx, key in COMPILED:
        m = rx.match(body)
        if not m:
            continue
        if key == "res":
            return [(f"res_{m.group(2).lower()}", float(m.group(1)))]
        if key == "res_all":
            v = float(m.group(1))
            return [(f"res_{s}", v) for s in ("fire", "nature", "frost", "shadow", "arcane")]
        if key == "wskill":
            skill = m.group(1).lower().replace("two-handed ", "2h_").replace(" ", "_")
            return [(f"wskill_{skill}", float(m.group(2)))]
        return [(key, float(m.group(1)))]
    return None


def normalize(raw: dict) -> dict:
    p = raw["preview_item"]
    stats: dict[str, float] = {}
    for s in p.get("stats", []):
        key = STAT_KEYS.get(s["type"]["type"])
        if key and not s.get("is_negated"):
            stats[key] = stats.get(key, 0) + s["value"]
    effects, unparsed = [], []
    for sp in p.get("spells", []):
        desc = sp.get("description", "")
        parsed = parse_effect(desc)
        if parsed:
            for k, v in parsed:
                stats[k] = stats.get(k, 0) + v
            effects.append(desc)
        elif desc:
            unparsed.append(desc)
    if p.get("armor"):
        stats["armor"] = p["armor"]["value"]
    if p.get("shield_block"):
        stats["block_value"] = stats.get("block_value", 0) + p["shield_block"]["value"]
    weapon = None
    w = p.get("weapon") or {}
    if w.get("damage") and w.get("attack_speed"):
        weapon = {
            "min": w["damage"]["min_value"], "max": w["damage"]["max_value"],
            "speed": round(w["attack_speed"]["value"] / 1000, 2),
            "dps": round((w.get("dps") or {}).get("value", 0), 2),
        }
    req = p.get("requirements", {})
    classes = [c["id"] for c in (req.get("playable_classes") or {}).get("links", [])]
    races = [r["id"] for r in (req.get("playable_races") or {}).get("links", [])]
    rep = req.get("reputation")
    skill = req.get("skill")
    return {
        "name": p["name"],
        "quality": p["quality"]["type"],
        "class": p["item_class"]["id"],
        "subclass": p["item_subclass"]["id"],
        "inventory_type": p["inventory_type"]["type"],
        "binding": (p.get("binding") or {}).get("type"),
        "item_level": raw.get("level"),
        "required_level": (req.get("level") or {}).get("value", raw.get("required_level", 0)),
        "stats": stats,
        "weapon": weapon,
        "effects": effects,
        "unparsed_effects": unparsed,
        "classes": classes or None,
        "races": races or None,
        "reputation": {"faction": rep["faction"]["name"], "faction_id": rep["faction"]["id"],
                       "level": rep["min_reputation_level"]} if rep else None,
        "skill": {"name": skill["profession"]["name"], "level": skill["level"]} if skill else None,
        "set": (p.get("set") or {}).get("item_set", {}).get("name"),
        "unique": bool(p.get("unique_equipped") or p.get("limit_category")),
        "temporary": bool(p.get("expiration_time_left")),
    }


def main():
    out = {}
    for path in (RAW / "blizzard" / "items").glob("*.json"):
        raw = json.loads(path.read_text(encoding="utf-8"))
        out[raw["id"]] = normalize(raw)
    write_json(STAGING / "blizzard.json", out, compact=True)
    unparsed = {}
    for item in out.values():
        for text in item["unparsed_effects"]:
            if text.startswith("Equip:"):
                unparsed[text] = unparsed.get(text, 0) + 1
    print(f"{len(out)} items; {len(unparsed)} distinct unparsed Equip effects")


if __name__ == "__main__":
    main()
