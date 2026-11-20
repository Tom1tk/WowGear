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
from _common import FOREVER, ROOT, STAGING, read_json, write_json  # noqa: E402

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
           "pvp_rep": 0.3, "pvp_rank": 0.3}
RECIPE_REALISM = {"trainer": 0.8, "automatic": 0.8, "vendor": 0.7, "quest": 0.6, "rep": 0.5, "favor": 0.5, "drop": 0.35, "unknown": 0.5}


def realism(src: dict) -> float:
    """How easy a source is for a normal player (1 = sure thing)."""
    base = REALISM.get(src["type"], 0.5)
    chance = src.get("chance")
    if src["type"] == "drop" and chance is not None:
        base = 0.9 if chance >= 10 else 0.75 if chance >= 3 else 0.55
    elif src["type"] == "drop" and not src.get("instance"):  # open-world drop, rate unknown: below a known rare rate
        base = 0.5
    if src["type"] == "craft":  # the recipe is the hard part
        base = RECIPE_REALISM.get((src.get("recipe") or {}).get("kind"), base)
    return base


class Builder:
    def __init__(self):
        self.scorer = Scorer()
        self.items = self.scorer.items
        self.sources = read_json(FOREVER / "sources.json")
        self.instances = {k: v for k, v in read_json(FOREVER / "instances.json").items() if not k.startswith("_")}
        self.entrances = read_json(STAGING / "questie.json").get("entrances", {})
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

    def source_level(self, src, item, faction: str, cls_id: str, extra: bool = True) -> tuple[int, int] | None:
        """(level the item can be had from this source, raid tier) or None. extra=False leaves out PvP rank rewards
        and rare open-world drops, which the page shows only when their filter / tickbox allows."""
        req = self.min_level(item)
        kind = src["type"]
        if kind == "pvp_rep":
            return None
        if kind == "pvp_rank" and not extra:
            return None
        if src.get("faction") and src["faction"] != faction:
            return None
        if kind == "quest":
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
            if src.get("chance") is not None and src["chance"] < 1 and not extra:
                return None  # rare open-world drop: not worth farming
            return req, 0
        if kind in ("world_drop", "vendor", "craft", "object", "container", "pvp_rank"):
            return req, 0
        return None

    def availability(self, iid, item, faction, cls_id, extra=False):
        """Best (lowest level, lowest tier) way to get the item + that source."""
        best = None
        for src in self.sources.get(iid, []):
            res = self.source_level(src, item, faction, cls_id, extra)
            if res is None:
                continue
            level, tier = res
            key = (tier, level, -realism(src))
            if best is None or key < best[0]:
                best = (key, level, tier, src)
        if not best:
            return None
        return best[1], best[2], best[3]

    def score(self, item, iid, weights, weapon_w, slot, race, cls_id=None, bonus=False, spec=None) -> float:
        return self.scorer.score(item, iid, weights, weapon_w, slot, race, cls_id, bonus, spec)

    # ---------- build ----------
    def build(self, cls_id: str, spec: str, faction: str) -> dict:
        cls = self.classes[cls_id]
        key = f"{cls['slug']}.{spec}"
        prof = self.profiles[self.aliases.get(key, key)]
        weapon_w = dict(prof.get("weapon", {}))
        races = [r for r in self.races.values() if r["faction"] == faction and int(cls_id) in r["classes"]]
        race = races[0] if len(races) == 1 else None  # racial skill only if the combo is unique

        cands = []  # (slot, iid, avail_level, tier, source, raw leveling, raw endgame, set-mode leveling, set-mode endgame, normal)
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
            normal = avail is not None  # False: only from PvP rank or a rare drop
            avail = avail or self.availability(iid, item, faction, cls_id, extra=True)
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
            x_lvl = self.score(item, iid, prof["leveling"], lw, slot, race, cls_id, True, key)
            x_end = self.score(item, iid, prof["endgame"], weapon_w, slot, race, cls_id, True, key)
            if max(s_lvl, s_end, x_lvl, x_end) <= 0:
                continue
            cands.append((slot, iid, level, tier, src, s_lvl, s_end, x_lvl, x_end, normal))

        by_slot: dict[str, list] = {}
        for c in cands:
            by_slot.setdefault(c[0], []).append(c)

        def top(slot, level, tier, idx, normal=False):
            pool = [c for c in by_slot.get(slot, []) if c[2] <= level and c[3] <= tier and c[idx] > 0 and (c[9] or not normal)]
            pool.sort(key=lambda c: (-c[idx] * (0.7 + 0.3 * realism(c[4])), c[2]))
            n = PAIRED.get(slot, 1) + TOP_N - 1
            return pool[:n]

        def entry(c, idx):
            """[id, raw score] or [id, raw score, set-mode score] when the set-mode score differs."""
            raw, extra = c[idx], c[idx + 2]
            return [c[1], raw] if raw == extra else [c[1], raw, extra]

        steps = [(lvl, 0) for lvl in LEVELS] + [(60, t) for t in self.tiers]
        slots = {}
        used = set()
        for slot in SLOT_ORDER:
            points = []
            last = None
            for lvl, tier in steps:
                idx = 5 if lvl < 60 else 6
                # raw-stat ranking first, then what only the set-mode ranking adds; each also without PvP / rare drops,
                # so the page still has TOP_N picks when those are filtered out
                picks = []
                for i, normal in ((idx, False), (idx, True), (idx + 2, False), (idx + 2, True)):
                    picks += [c for c in top(slot, lvl, tier, i, normal) if c not in picks]
                sig = [c[1] for c in picks]
                if sig != last:
                    points.append({"level": lvl, "tier": tier, "items": [entry(c, idx) for c in picks]})
                    used.update(sig)
                    last = sig
            if any(p["items"] for p in points):
                slots[slot] = points

        # set pieces that never make a top list, so the planner can still plan the whole set (leveling scores)
        listed, extra = set(used), {}
        for c in cands:
            sid = self.items[c[1]].get("set")
            if c[1] not in listed and sid and any(p in listed for p in map(str, self.scorer.sets[str(sid)]["pieces"])):
                extra.setdefault(c[0], []).append(entry(c, 5))
                used.add(c[1])

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
                                  key=lambda s: (-realism(s), -(s.get("chance") or 0), not s.get("loc")))[:4],
                "checks": item.get("checks", {}),
            }
            usable = [s for s in srcs if self.source_level(s, item, faction, cls_id)]
            unc = list(item.get("uncertain", []))
            eff = self.scorer.effect_entry(iid, cls_id, key)
            unscored = list(item.get("unscored", []))
            if eff:  # a cited use-effect value is scored in set mode: no longer "unscored"
                unscored = [u for u in unscored if not u.startswith("Use:")]
                if eff.get("uncertain"):
                    unc.append(eff["uncertain"])
            if item.get("set"):
                sdef = self.scorer.sets[str(item["set"])]
                item_info[iid]["set"] = {"name": sdef["name"], "pieces": sdef["pieces"],
                                         "bonuses": [{k: b[k] for k in ("count", "text", "scored")}
                                                     for b in self.scorer.set_bonuses_for(item, cls_id)]}
                unc += sdef.get("uncertain", [])
            if unscored:
                item_info[iid]["unscored"] = unscored
            if item.get("random_enchant"):
                item_info[iid]["random_enchant"] = item["random_enchant"]
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
            "slots": slots, "extra": extra, "items": item_info,
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

    def entrance(self, key: str, name: str) -> dict | None:
        """Dungeon entrance from QuestieDB Forever. Only the original dungeons: Questie's Forever-new ones are missing,
        and its 'Hyjal Summit' is the Caverns of Time raid, not Forever's Mount Hyjal one."""
        if self.instances[key].get("zone") == "Mount Hyjal":
            return None
        wing = {"sm_": "Scarlet Monastery", "dire_maul_": "Dire Maul", "lower_blackrock": "Blackrock Spire",
                "upper_blackrock": "Blackrock Spire", "sunken_temple": "The Temple of Atal'Hakkar"}
        name = next((v for k, v in wing.items() if key.startswith(k)), name)
        return self.entrances.get(name)

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
                              "side": v.get("side"), "uncertain": v.get("uncertain", []),
                              "entrance": self.entrance(k, v["name"])}
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
