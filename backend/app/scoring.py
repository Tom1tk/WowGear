"""Item rules and scoring shared by the web app and the offline gear builder.

The data files live in data/era/ (made by scripts/data/). This module only
reads them: class armor/weapon rules, stat weights, hand-kept special
effects, and the merged item table.
"""

from __future__ import annotations

import json
from functools import cached_property
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data" / "era"

ARMOR_SLOTS = {
    "HEAD": "head", "NECK": "neck", "SHOULDER": "shoulders", "CLOAK": "back",
    "CHEST": "chest", "ROBE": "chest", "WRIST": "wrist", "HAND": "hands",
    "WAIST": "waist", "LEGS": "legs", "FEET": "feet", "FINGER": "ring",
    "TRINKET": "trinket",
}
WEAPON_SLOTS = ("main_hand", "off_hand", "two_hand")


def _load(name: str) -> dict:
    with (DATA / name).open(encoding="utf-8") as fh:
        return json.load(fh)


def _strip_meta(data: dict) -> dict:
    return {k: v for k, v in data.items() if not k.startswith("_")}


class Scorer:
    """Rules + stat weights. Data files load lazily and stay cached."""

    @cached_property
    def class_data(self) -> dict:
        return _load("classes.json")

    @property
    def classes(self) -> dict:
        return self.class_data["classes"]

    @property
    def races(self) -> dict:
        return self.class_data["races"]

    @property
    def wskill_names(self) -> dict:
        return self.class_data["weapon_skill_names"]

    @cached_property
    def weights(self) -> dict:
        return _load("weights.json")

    @cached_property
    def effects(self) -> dict:
        return _strip_meta(_load("effects.json"))

    @cached_property
    def items(self) -> dict:
        return _load("items.json")

    # ---------- lookups ----------
    def class_id(self, slug_or_name: str) -> str | None:
        key = (slug_or_name or "").strip().lower()
        for cid, cls in self.classes.items():
            if key in (cls["slug"], cls["name"].lower(), cid):
                return cid
        return None

    def profile(self, cls_id: str, spec: str) -> dict:
        key = f"{self.classes[cls_id]['slug']}.{spec}"
        aliases = self.weights["aliases"]
        return self.weights["profiles"][aliases.get(key, key)]

    # ---------- rules ----------
    @staticmethod
    def slot_of(item: dict) -> str | None:
        inv = item["inventory_type"]
        if inv in ARMOR_SLOTS:
            return ARMOR_SLOTS[inv]
        if inv == "TWOHWEAPON":
            return "two_hand"
        if inv in ("WEAPON", "WEAPONMAINHAND"):
            return "main_hand"
        if inv in ("WEAPONOFFHAND", "SHIELD", "HOLDABLE"):
            return "off_hand"
        if inv in ("RANGED", "RANGEDRIGHT", "THROWN"):
            return "ranged"
        if inv == "RELIC":
            return "relic"
        return None

    def usable_from(self, item: dict, cls_id: str) -> int | None:
        """Lowest level at which the class can equip the item (None = never)."""
        cls = self.classes[cls_id]
        if item.get("classes") and int(cls_id) not in item["classes"]:
            return None
        if item.get("skill"):  # needs a profession skill (e.g. Engineering)
            return None
        if item["class"] == 4:
            sub = item["subclass"]
            if sub == 0:  # misc: rings, necks, trinkets, off-hand frills
                return 1
            if sub == 1 and item["inventory_type"] in ("CLOAK", "NECK", "FINGER", "TRINKET"):
                return 1
            if item["inventory_type"] == "RELIC" and cls.get("relic") != sub:
                return None
            for armor_sub, level in cls["armor"]:
                if armor_sub == sub:
                    return level
            return None
        if item["class"] == 2:
            sub = item["subclass"]
            if sub not in cls["weapons"]:
                return None
            if item["inventory_type"] in ("RANGED", "RANGEDRIGHT", "THROWN") and sub not in cls["ranged"]:
                return None
            if item["inventory_type"] == "WEAPONOFFHAND" and not cls.get("dual_wield"):
                return None
            return 1
        return None

    @staticmethod
    def min_level(item: dict) -> int:
        """Required level; items without one get a floor from their item level
        (e.g. ilvl 55 'Hakkari' items with no level requirement)."""
        req = item.get("required_level") or 0
        if req == 0 and (item.get("item_level") or 0) > 10:
            req = min(60, item["item_level"] - 5)
        return req

    # ---------- scoring ----------
    def score(self, item: dict, iid: str, weights: dict, weapon_w: dict, slot: str,
              race: dict | None = None, cls_id: str | None = None) -> float:
        """Equivalence points of an item for one weight set."""
        stats = dict(item.get("stats") or {})
        eff = self.effects.get(str(iid)) or {}
        if not eff.get("classes") or (cls_id and int(cls_id) in eff["classes"]):
            for k, v in eff.get("stats", {}).items():
                stats[k] = stats.get(k, 0) + v
        total = 0.0
        for key, value in stats.items():
            if key.startswith("wskill_"):
                total += value * weights.get("wskill", 0) * 0.5
            else:
                total += value * weights.get(key, 0)
        wpn = item.get("weapon")
        if wpn and slot in WEAPON_SLOTS:
            per = weapon_w.get("offhand_dps", 0) if slot == "off_hand" else weapon_w.get("dps", 0)
            total += wpn["dps"] * per
            if slot != "off_hand" and weapon_w.get("slow_bonus"):
                total += max(0.0, min(wpn["speed"], 3.8) - 2.5) * weapon_w["slow_bonus"]
            skill = self.wskill_names.get(str(item["subclass"]))
            bonus = (race or {}).get("weapon_skill", {}).get(skill)
            if bonus and weapon_w.get("dps"):
                total += bonus * weights.get("wskill", 0)
        if wpn and slot == "ranged":
            if weapon_w.get("ranged_dps"):
                total += wpn["dps"] * weapon_w["ranged_dps"]
            elif item["subclass"] == 19:  # wand: a leveling caster's filler damage
                total += wpn["dps"] * weapon_w.get("wand_dps", 0)
        return round(total, 1)

    def score_for(self, iid: str, cls_id: str, spec: str, level: int,
                  race_id: str | None = None) -> float | None:
        """Score of one item for a character (None if unknown or unusable)."""
        item = self.items.get(str(iid))
        if not item:
            return None
        slot = self.slot_of(item)
        if not slot or self.usable_from(item, cls_id) is None:
            return None
        prof = self.profile(cls_id, spec)
        weapon_w = dict(prof.get("weapon", {}))
        weights = prof["endgame"] if level >= 60 else prof["leveling"]
        if level < 60 and self.classes[cls_id]["ranged"] == [19]:
            weapon_w["wand_dps"] = 2.0
        race = self.races.get(str(race_id)) if race_id else None
        return self.score(item, str(iid), weights, weapon_w, slot, race, cls_id)


scorer = Scorer()
