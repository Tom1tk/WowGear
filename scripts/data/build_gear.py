"""Build the per-level best-in-slot gear files the web app serves.

For every class + spec + faction, each usable item gets a score from the
spec's stat weights (data/era/weights.json). For each level 10..60 the best
items per slot are the highest-scoring items the character can equip and
realistically get by that level. At level 60 there are extra tiers:
0 = pre-raid, 1 = Molten Core / Onyxia / world bosses, 2 = + Blackwing Lair /
Zul'Gurub, 3 = + Ahn'Qiraj, 4 = + Naxxramas.

Output: data/era/gear/<class>.<spec>.<A|H>.json. Only the levels where a
slot's top list changes are stored ("breakpoints").

    python scripts/data/build_gear.py [--only druid.feral_cat]
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import ERA, read_json, write_json  # noqa: E402

LEVELS = range(10, 61)
TIERS = (0, 1, 2, 3, 4)
TOP_N = 3
QUEST_EARLY = 3   # a quest reward is usually earned ~3 levels below quest level
ARMOR_SLOTS = {
    "HEAD": "head", "NECK": "neck", "SHOULDER": "shoulders", "CLOAK": "back",
    "CHEST": "chest", "ROBE": "chest", "WRIST": "wrist", "HAND": "hands",
    "WAIST": "waist", "LEGS": "legs", "FEET": "feet", "FINGER": "ring",
    "TRINKET": "trinket",
}
SLOT_ORDER = ["head", "neck", "shoulders", "back", "chest", "wrist", "hands", "waist",
              "legs", "feet", "ring", "trinket", "main_hand", "off_hand", "two_hand",
              "ranged", "relic"]
PAIRED = {"ring": 2, "trinket": 2}
REALISM = {"quest": 1.0, "vendor": 1.0, "drop": 0.9, "boss": 0.9, "object": 0.8,
           "container": 0.7, "craft": 0.75, "instance_trash": 0.5, "world_drop": 0.35,
           "pvp_rep": 0.3}


def realism(src: dict) -> float:
    """How easy a source is for a normal player (1 = sure thing)."""
    base = REALISM.get(src["type"], 0.5)
    chance = src.get("chance")
    if src["type"] == "drop" and chance is not None:
        base = 0.9 if chance >= 10 else 0.75 if chance >= 3 else 0.55
    if src["type"] == "craft" and not src.get("recipe"):
        base = 0.8  # trainer recipe
    return base


class Builder:
    def __init__(self):
        self.items = read_json(ERA / "items.json")
        self.sources = read_json(ERA / "sources.json")
        self.instances = {k: v for k, v in read_json(ERA / "instances.json").items() if not k.startswith("_")}
        cls = read_json(ERA / "classes.json")
        self.classes = cls["classes"]
        self.races = cls["races"]
        self.wskill_names = cls["weapon_skill_names"]
        w = read_json(ERA / "weights.json")
        self.profiles, self.aliases = w["profiles"], w["aliases"]
        self.effects = {k: v for k, v in read_json(ERA / "effects.json").items() if not k.startswith("_")}
        for iid, eff in self.effects.items():
            name = (self.items.get(iid) or {}).get("name")
            if name and name != eff["name"]:
                print(f"WARN effects.json {iid}: '{eff['name']}' but item data says '{name}'")

    # ---------- rules ----------
    def slot_of(self, item, cls) -> str | None:
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

    def usable_from(self, item, cls_id: str) -> int | None:
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

    def source_level(self, src, item, faction: str, cls_id: str) -> tuple[int, int] | None:
        """(level the item can be had from this source, raid tier) or None."""
        req = self.min_level(item)
        kind = src["type"]
        if kind in ("pvp_rank", "pvp_rep"):
            return None  # PvP rewards are left out of the PvE lists
        if src.get("faction") and src["faction"] != faction:
            return None
        if kind == "quest":
            mask = src.get("classes_mask")
            if mask and not mask & (1 << (int(cls_id) - 1)):
                return None
            level = max(req, src.get("min_level") or 1, (src.get("level") or 1) - QUEST_EARLY)
            inst = self.instances.get(src.get("instance") or "")
            return max(level, inst["levels"][0]) if inst else level, (inst or {}).get("tier", 0)
        inst_key = src.get("instance")
        if kind == "craft" and inst_key in self.instances:
            return max(req, 60), self.instances[inst_key].get("tier", 0)
        if inst_key and inst_key in self.instances:
            inst = self.instances[inst_key]
            if inst.get("side") and inst["side"] != faction:
                return None
            return max(req, inst["levels"][0]), inst.get("tier", 0)
        if kind == "drop":
            lvl = (src.get("level") or [0, 0])[0] or 0
            if src.get("chance") is not None and src["chance"] < 1 and src.get("rank") in ("normal", "elite"):
                return None  # rare drop from a normal mob: not worth farming
            return max(req, lvl - 2), 0
        if kind in ("world_drop", "vendor", "craft", "object", "container", "pvp_rep"):
            return req, 0
        return None

    @staticmethod
    def min_level(item) -> int:
        """Required level; items without one get a floor from their item level
        (e.g. ilvl 55 'Hakkari' items with no level requirement)."""
        req = item.get("required_level") or 0
        if req == 0 and (item.get("item_level") or 0) > 10:
            req = min(60, item["item_level"] - 5)
        return req

    def availability(self, iid, item, faction, cls_id):
        """Best (lowest level, lowest tier) way to get the item + that source."""
        best = None
        for src in self.sources.get(iid, []):
            res = self.source_level(src, item, faction, cls_id)
            if res is None:
                continue
            level, tier = res
            key = (tier, level, -realism(src))
            if best is None or key < best[0]:
                best = (key, level, tier, src)
        if not best:
            return None
        return best[1], best[2], best[3]

    # ---------- scoring ----------
    def score(self, item, iid, weights, weapon_w, slot, race, cls_id=None) -> float:
        stats = dict(item.get("stats") or {})
        eff = self.effects.get(iid) or {}
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
        if wpn and slot in ("main_hand", "two_hand", "off_hand"):
            per = weapon_w.get("offhand_dps", 0) if (slot == "off_hand") else weapon_w.get("dps", 0)
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

    # ---------- build ----------
    def build(self, cls_id: str, spec: str, faction: str) -> dict:
        cls = self.classes[cls_id]
        key = f"{cls['slug']}.{spec}"
        prof = self.profiles[self.aliases.get(key, key)]
        weapon_w = dict(prof.get("weapon", {}))
        races = [r for r in self.races.values() if r["faction"] == faction and int(cls_id) in r["classes"]]
        race = races[0] if len(races) == 1 else None  # racial skill only if the combo is unique

        cands = []  # (slot, iid, avail_level, tier, source, score_leveling, score_endgame)
        for iid, item in self.items.items():
            if item.get("races") and not any(r for r in item["races"]):
                continue
            slot = self.slot_of(item, cls)
            if not slot:
                continue
            if slot == "relic" and cls.get("relic") != item["subclass"]:
                continue
            if slot == "two_hand" and item["class"] == 2 and item["subclass"] not in cls["weapons"]:
                continue
            equip = self.usable_from(item, cls_id)
            if equip is None:
                continue
            avail = self.availability(iid, item, faction, cls_id)
            if not avail:
                continue
            level, tier, src = avail
            level = max(level, equip, self.min_level(item))
            if level > 60:
                continue
            lw = dict(weapon_w)
            if cls["ranged"] == [19]:
                lw["wand_dps"] = 2.0
            s_lvl = self.score(item, iid, prof["leveling"], lw, slot, race, cls_id)
            s_end = self.score(item, iid, prof["endgame"], weapon_w, slot, race, cls_id)
            if s_lvl <= 0 and s_end <= 0:
                continue
            cands.append((slot, iid, level, tier, src, s_lvl, s_end))

        by_slot: dict[str, list] = {}
        for c in cands:
            by_slot.setdefault(c[0], []).append(c)

        def top(slot, level, tier):
            idx = 5 if level < 60 else 6
            pool = [c for c in by_slot.get(slot, []) if c[2] <= level and c[3] <= tier and c[idx] > 0]
            pool.sort(key=lambda c: (-c[idx] * (0.7 + 0.3 * realism(c[4])), c[2]))
            n = PAIRED.get(slot, 1) + TOP_N - 1
            return [(c[1], c[idx]) for c in pool[:n]]

        steps = [(lvl, 0) for lvl in LEVELS] + [(60, t) for t in TIERS[1:]]
        slots = {}
        used = set()
        for slot in SLOT_ORDER:
            points = []
            last = None
            for lvl, tier in steps:
                picks = top(slot, lvl, tier)
                sig = [p[0] for p in picks]
                if sig != last:
                    points.append({"level": lvl, "tier": tier, "items": [[i, s] for i, s in picks]})
                    used.update(sig)
                    last = sig
            if any(p["items"] for p in points):
                slots[slot] = points

        item_info = {}
        for iid in used:
            item = self.items[iid]
            srcs = self.sources.get(iid, [])
            item_info[iid] = {
                "name": item["name"], "quality": item["quality"],
                "required_level": item.get("required_level", 0),
                "binding": item.get("binding"),
                "stats": item.get("stats", {}), "weapon": item.get("weapon"),
                "subclass": item["subclass"], "class": item["class"],
                "inventory_type": item["inventory_type"],
                "effects": item.get("effects", []),
                "special": (self.effects.get(iid) or {}).get("note")
                           or ("; ".join(item["unparsed_effects"]) if item.get("unparsed_effects") else None),
                "unique": item.get("unique", False),
                "sources": [s for s in srcs if self.source_level(s, item, faction, cls_id)][:4],
                "stats_check": item.get("stats_check"),
            }
        return {
            "class": cls["name"], "class_id": int(cls_id), "spec": spec,
            "spec_name": cls["specs"][spec]["name"], "role": cls["specs"][spec]["role"],
            "faction": faction, "profile": self.aliases.get(key, key),
            "weights": {"leveling": prof["leveling"], "endgame": prof["endgame"], "weapon": weapon_w,
                        "sources": prof.get("sources", [])},
            "slots": slots, "items": item_info,
        }

    def run(self, only: str | None = None):
        out_dir = ERA / "gear"
        count = 0
        for cls_id, cls in self.classes.items():
            factions = sorted({r["faction"] for r in self.races.values() if int(cls_id) in r["classes"]})
            for spec in cls["specs"]:
                key = f"{cls['slug']}.{spec}"
                if only and key != only:
                    continue
                for faction in factions:
                    data = self.build(cls_id, spec, faction)
                    write_json(out_dir / f"{key}.{faction}.json", data, compact=True)
                    count += 1
        print(f"wrote {count} gear files")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    Builder().run(ap.parse_args().only)
