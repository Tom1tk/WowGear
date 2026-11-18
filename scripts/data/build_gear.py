"""Build the per-level best-in-slot gear files the web app serves.

For every class + spec + faction, each usable item gets a score from the
spec's stat weights (data/forever/weights.json). For each level 10..60 the best
items per slot are the highest-scoring items the character can equip and
realistically get by that level. At level 60 there are extra tiers: 0 = pre-raid,
1 = raid tier 1 (Barrow Deeps, Hyjal Summit, Onyxia's Lair); more tiers come from
instances.json.

Output: frontend/data/gear/<class>.<spec>.<A|H>.json. Only the levels where a
slot's top list changes are stored ("breakpoints").

    python scripts/data/build_gear.py [--only druid.feral_cat]
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import FOREVER, ROOT, read_json, write_json  # noqa: E402

sys.path.insert(0, str(ROOT))
from backend.app.scoring import Scorer  # noqa: E402

OUT = ROOT / "frontend" / "data"

LEVELS = range(10, 61)
TIER_NOTES = {1: "Raids open 9 Dec 2026. Loot lists are incomplete until the raids are datamined or released."}
DATAMINED = "Raid loot before the raids open (9 Dec 2026) is datamined and may change."
TOP_N = 3
QUEST_EARLY = 3   # a quest reward is usually earned ~3 levels below quest level
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
        self.scorer = Scorer()
        self.items = self.scorer.items
        self.sources = read_json(FOREVER / "sources.json")
        self.instances = {k: v for k, v in read_json(FOREVER / "instances.json").items() if not k.startswith("_")}
        self.classes = self.scorer.classes
        self.races = self.scorer.races
        self.profiles = self.scorer.weights["profiles"]
        self.aliases = self.scorer.weights["aliases"]
        self.effects = self.scorer.effects
        self.tiers = sorted({v.get("tier", 0) for v in self.instances.values()} - {0})
        for iid, eff in self.effects.items():
            name = (self.items.get(iid) or {}).get("name")
            if name and name != eff["name"]:
                print(f"WARN effects.json {iid}: '{eff['name']}' but item data says '{name}'")

    # ---------- rules (shared with the web app) ----------
    def slot_of(self, item, cls=None) -> str | None:
        return self.scorer.slot_of(item)

    def usable_from(self, item, cls_id: str) -> int | None:
        return self.scorer.usable_from(item, cls_id)

    def min_level(self, item) -> int:
        return self.scorer.min_level(item)

    def source_level(self, src, item, faction: str, cls_id: str) -> tuple[int, int] | None:
        """(level the item can be had from this source, raid tier) or None."""
        req = self.min_level(item)
        kind = src["type"]
        if kind in ("pvp_rank", "pvp_rep"):
            return None  # PvP rewards are left out of the PvE lists
        if src.get("faction") and src["faction"] != faction:
            return None
        if kind == "quest":
            level = max(req, (src.get("level") or 1) - QUEST_EARLY)
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
            if src.get("chance") is not None and src["chance"] < 1:
                return None  # rare open-world drop: not worth farming
            return req, 0
        if kind in ("world_drop", "vendor", "craft", "object", "container", "pvp_rep"):
            return req, 0
        return None

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

    def score(self, item, iid, weights, weapon_w, slot, race, cls_id=None) -> float:
        return self.scorer.score(item, iid, weights, weapon_w, slot, race, cls_id)

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
            if item.get("races") and not any(int(cls_id) in r["classes"] and int(rid) in item["races"]
                                             for rid, r in self.races.items() if r["faction"] == faction):
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

        steps = [(lvl, 0) for lvl in LEVELS] + [(60, t) for t in self.tiers]
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
                "sources": sorted((s for s in srcs if self.source_level(s, item, faction, cls_id)),
                                  key=lambda s: -realism(s))[:4],
                "checks": item.get("checks", {}),
            }
            usable = [s for s in srcs if self.source_level(s, item, faction, cls_id)]
            unc = list(item.get("uncertain", []))
            if any(self.instances.get(s.get("instance") or "", {}).get("tier", 0) for s in usable):
                unc.append(DATAMINED)
            if usable and all(s.get("uncertain") for s in usable):
                unc.append(usable[0]["uncertain"])
            item_info[iid]["uncertain"] = unc
        return {
            "class": cls["name"], "class_id": int(cls_id), "spec": spec,
            "spec_name": cls["specs"][spec]["name"], "role": cls["specs"][spec]["role"],
            "faction": faction, "profile": self.aliases.get(key, key),
            "weights": {"leveling": prof["leveling"], "endgame": prof["endgame"], "weapon": weapon_w,
                        "sources": prof.get("sources", [])},
            "slots": slots, "items": item_info,
        }

    def run(self, only: str | None = None):
        out_dir = OUT / "gear"
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
        self.write_meta()
        print(f"wrote {count} gear files + meta.json")

    def write_meta(self):
        """Small lookup file for the frontend: classes, specs, races, instances, tiers."""
        import datetime
        import re
        meta = {
            "built": datetime.date.today().isoformat(), "game": "forever",
            "classes": {cid: {"name": c["name"], "slug": c["slug"],
                              "specs": {k: v["name"] for k, v in c["specs"].items()},
                              "leveling_spec": self.scorer.weights["leveling_default"][c["slug"]]}
                        for cid, c in self.classes.items()},
            "races": {rid: {"name": r["name"], "slug": re.sub(r"\W+", "_", r["name"].lower()),
                            "faction": r["faction"], "classes": r["classes"]} for rid, r in self.races.items()},
            "instances": {k: {"name": v["name"], "type": v["type"], "levels": v["levels"],
                              "zone": v.get("zone"), "tier": v.get("tier", 0), "note": v.get("note"),
                              "side": v.get("side"), "uncertain": v.get("uncertain", [])}
                          for k, v in self.instances.items()},
            "tiers": {str(t): f"Raid tier {t}: " + ", ".join(
                          re.sub(r"^The ", "", v["name"]) for v in self.instances.values() if v.get("tier") == t)
                      for t in self.tiers},
            "tier_notes": {str(t): TIER_NOTES[t] for t in self.tiers if t in TIER_NOTES},
        }
        write_json(OUT / "meta.json", meta)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    Builder().run(ap.parse_args().only)
