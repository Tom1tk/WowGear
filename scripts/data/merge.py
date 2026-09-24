"""Merge all staged sources into the data files the web app reads.

Inputs (data/era/staging/, made by the parse_*.py scripts):
  blizzard.json  - Source A: Blizzard Game Data API, Classic Era (stats, rules)
  questie.json   - Source B: QuestieDB Classic Era (drops, quests, vendors, NPCs)
  cmangos.json   - Source C: CMaNGOS classic-db, patch 1.12 (stats, loot, quests)
  vmangos.json   - Source D: VMaNGOS world DB, patch 1.12 (stats, loot, quests)
  atlasloot.json - Source E: AtlasLootClassic (boss loot, crafting, level ranges)
plus the hand-kept data/era/instances.json.

Outputs:
  data/era/items.json    - equippable items with stats, rules and confidence
  data/era/sources.json  - where each item comes from, with provenance
  reports/conflicts.md   - facts the sources disagree on
  reports/instances.md   - instance level ranges vs boss levels

Rule: a fact is "confirmed" when two independent sources agree.

    python scripts/data/merge.py
"""

from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from _common import ERA, REPORTS, STAGING, read_json, write_json  # noqa: E402

EQUIP_TYPES = {
    "HEAD", "NECK", "SHOULDER", "CLOAK", "CHEST", "ROBE", "WRIST", "HAND", "WAIST",
    "LEGS", "FEET", "FINGER", "TRINKET", "WEAPON", "TWOHWEAPON", "WEAPONMAINHAND",
    "WEAPONOFFHAND", "SHIELD", "HOLDABLE", "RANGED", "RANGEDRIGHT", "THROWN", "RELIC",
}
MANGOS_STATS = {"3": "agi", "4": "str", "5": "int", "6": "spi", "7": "sta"}
QUALITY = {"UNCOMMON": 2, "RARE": 3, "EPIC": 4, "LEGENDARY": 5}
ALLIANCE_RACES = 1 | 4 | 8 | 64
HORDE_RACES = 2 | 16 | 32 | 128
WORLD_DROP_NPCS = 12  # more droppers than this = a random "world drop"
RANK_NAMES = {0: "normal", 1: "elite", 2: "rare elite", 3: "boss", 4: "rare"}


def pretty_zone(code: str | None) -> str | None:
    if not code:
        return None
    small = {"Of", "The", "And"}
    words = code.replace("_", " ").title().split()
    return " ".join(w.lower() if i and w in small else w for i, w in enumerate(words))


def faction_of_races(mask) -> str | None:
    if not mask:
        return None
    a, h = bool(mask & ALLIANCE_RACES), bool(mask & HORDE_RACES)
    return "A" if a and not h else "H" if h and not a else None


class Merger:
    def __init__(self):
        self.blz = read_json(STAGING / "blizzard.json")
        self.q = read_json(STAGING / "questie.json")
        self.cm = read_json(STAGING / "cmangos.json")
        self.vm = read_json(STAGING / "vmangos.json")
        self.al = read_json(STAGING / "atlasloot.json")
        self.instances = {k: v for k, v in read_json(ERA / "instances.json").items() if not k.startswith("_")}
        self.conflicts: list[str] = []
        self.recipe_items = self._recipe_index()
        self._index_instances()

    def _recipe_index(self) -> dict:
        """Recipe item name ('Plans: Heartseeker') -> how to get the recipe."""
        out = {}
        prefixes = ("Plans: ", "Pattern: ", "Schematic: ", "Formula: ", "Recipe: ")
        for rid, rec in self.q["item"].items():
            name = rec.get("name") or ""
            for pre in prefixes:
                if name.startswith(pre):
                    how = []
                    if rec.get("vendors"):
                        how.append("vendor")
                    if rec.get("npcDrops") or rec.get("objectDrops"):
                        how.append("drop")
                    if rec.get("questRewards"):
                        how.append("quest")
                    out[name[len(pre):].lower()] = {"id": int(rid), "name": name, "from": how}
        return out

    # ---------- instances ----------
    def _index_instances(self):
        self.area_to_instance = {}
        self.npc_to_instance = {}
        self.al_boss_items = defaultdict(set)  # (instance, npc or name) -> items
        for key, inst in self.instances.items():
            for area in inst.get("areas", []):
                self.area_to_instance.setdefault(int(area), key)
            al = self.al["instances"].get(inst.get("atlasloot") or "")
            if not al:
                continue
            for boss in al["bosses"]:
                if boss["npc"]:
                    self.npc_to_instance[boss["npc"]] = key
                ref = boss["npc"] or f"{key}:{boss['name']}"
                for item in boss["items"]:
                    self.al_boss_items[item].add((key, ref, boss["name"]))

    def instance_of_npc(self, npc_id: int) -> str | None:
        if npc_id in self.npc_to_instance:
            return self.npc_to_instance[npc_id]
        rec = self.q["npc"].get(str(npc_id)) or {}
        for area in [rec.get("zoneID")] + list(rec.get("spawns") or []):
            if area and int(area) in self.area_to_instance:
                return self.area_to_instance[int(area)]
        maps = (self.cm["npc"].get(str(npc_id)) or {}).get("maps") or []
        return None if not maps else None

    def instance_report(self) -> list[str]:
        lines = ["# Instance level ranges vs boss levels", "",
                 "Source 1: data/era/instances.json (AtlasLootClassic ranges where present).",
                 "Source 2: levels of the instance's bosses in QuestieDB.",
                 "A range is **confirmed** when the highest boss level is inside the range (+/- 3).", "",
                 "| Instance | Range | AtlasLoot | Boss levels | Check |", "|---|---|---|---|---|"]
        for key, inst in self.instances.items():
            al = self.al["instances"].get(inst.get("atlasloot") or "") or {}
            levels = []
            for boss in al.get("bosses", []):
                rec = self.q["npc"].get(str(boss["npc"])) if boss["npc"] else None
                if rec and rec.get("maxLevel"):
                    levels.append(rec["maxLevel"])
            lo, hi = inst["levels"]
            top = max(levels) if levels else None
            ok = top is not None and lo - 3 <= top <= hi + 3
            inst["check"] = "confirmed" if ok else ("single-source" if top is None else "conflict")
            alr = al.get("level_range")
            if alr and (alr[1], alr[2]) != (lo, hi):
                inst["check"] = "conflict"
            lines.append(f"| {inst['name']} | {lo}-{hi} | {alr[1:] if alr else '-'} | "
                         f"{min(levels) if levels else '-'}-{top if top else '-'} | {inst['check']} |")
        return lines

    # ---------- items ----------
    def compare_stats(self, iid: str, blz: dict) -> tuple[str, list[str]]:
        notes = []
        agree = 0
        seen = 0
        for label, src in (("CMaNGOS", self.cm), ("VMaNGOS", self.vm)):
            e = src["items"].get(iid)
            if not e:
                continue
            seen += 1
            diffs = []
            for mid, key in MANGOS_STATS.items():
                if (e["stats"].get(mid) or 0) != (blz["stats"].get(key) or 0):
                    diffs.append(f"{key} {e['stats'].get(mid, 0)} vs {blz['stats'].get(key, 0)}")
            if (e.get("required_level") or 0) != (blz.get("required_level") or 0):
                diffs.append(f"required level {e.get('required_level')} vs {blz.get('required_level')}")
            if (e.get("armor") or 0) != (blz["stats"].get("armor") or 0) and blz["class"] == 4 and blz["subclass"] != 6:
                diffs.append(f"armor {e.get('armor')} vs {blz['stats'].get('armor', 0)}")
            if blz.get("weapon") and e.get("dmg") and e["dmg"][0] and \
                    (round(e["dmg"][0]), round(e["dmg"][1])) != (blz["weapon"]["min"], blz["weapon"]["max"]):
                diffs.append(f"damage {e['dmg']} vs {[blz['weapon']['min'], blz['weapon']['max']]}")
            if diffs:
                notes.append(f"{label}: " + "; ".join(diffs))
            else:
                agree += 1
        if agree:
            return "confirmed", notes
        if seen:
            return "era-changed", notes  # Blizzard (current Era) wins over 1.12 data
        return "single-source", notes

    def is_random_suffix(self, iid: str, blz: dict) -> bool:
        for src in (self.cm, self.vm):
            e = src["items"].get(iid)
            if e and e.get("random_property"):
                return True
        return False

    def honor_rank(self, iid: str) -> int:
        return max((src["items"].get(iid) or {}).get("honor_rank") or 0 for src in (self.cm, self.vm))

    # ---------- sources ----------
    def npc_info(self, npc_id: int) -> dict:
        q = self.q["npc"].get(str(npc_id)) or {}
        c = self.cm["npc"].get(str(npc_id)) or self.vm["npc"].get(str(npc_id)) or {}
        zone = q.get("zoneID") or (q.get("spawns") or [None])[0]
        return {
            "name": q.get("name") or c.get("name") or f"NPC {npc_id}",
            "level": [q.get("minLevel") or c.get("min_level"), q.get("maxLevel") or c.get("max_level")],
            "rank": RANK_NAMES.get(q.get("rank", c.get("rank")), "normal"),
            "zone": pretty_zone(self.q["zones"].get(str(zone))) if zone else None,
            "friendly": q.get("friendlyToFaction"),
            "title": q.get("subName"),
        }

    def sources_for(self, iid: str, blz: dict) -> list[dict]:
        q_item = self.q["item"].get(iid) or {}
        found: dict[tuple, dict] = {}

        def add(kind, ref, dataset, **extra):
            rec = found.setdefault((kind, ref), {"type": kind, "id": ref, "found_in": set(), "chance": []})
            rec["found_in"].add(dataset)
            if extra.get("chance") is not None:
                rec["chance"].append(extra["chance"])

        for npc in q_item.get("npcDrops") or []:
            add("drop", int(npc), "QuestieDB")
        for obj in q_item.get("objectDrops") or []:
            add("object", int(obj), "QuestieDB")
        for cont in q_item.get("itemDrops") or []:
            add("container", int(cont), "QuestieDB")
        for quest in q_item.get("questRewards") or []:
            add("quest", int(quest), "QuestieDB")
        for vendor in q_item.get("vendors") or []:
            add("vendor", int(vendor), "QuestieDB")
        for label, src in (("CMaNGOS", self.cm), ("VMaNGOS", self.vm)):
            for key, chance in (src["drops"].get(iid) or {}).items():
                kind, _, ref = key.partition(":")
                kind = {"npc": "drop", "object": "object", "item": "container"}[kind]
                add(kind, int(ref), label, chance=chance)
            for quest in src["quest_rewards"].get(iid) or []:
                add("quest", int(quest), label)
            for vendor in src["vendors"].get(iid) or []:
                add("vendor", int(vendor), label)
        for inst, ref, boss_name in self.al_boss_items.get(int(iid), ()):
            if isinstance(ref, int):
                add("drop", ref, "AtlasLoot")
            else:
                add("boss", ref, "AtlasLoot")
                found[("boss", ref)]["instance"] = inst
                found[("boss", ref)]["name"] = boss_name
        for prof, crafted in self.al["crafting"].items():
            info = crafted.get(iid)
            if not info:
                continue
            add("craft", info["profession"], "AtlasLoot")
            rec = found[("craft", info["profession"])]
            rec["skill"] = info["skill"]
            recipe = self.recipe_items.get(blz["name"].lower())
            if recipe:
                add("craft", info["profession"], "QuestieDB (recipe item)")
                rec["recipe"] = recipe
        return self._shape(iid, blz, list(found.values()))

    def _shape(self, iid, blz, raw: list[dict]) -> list[dict]:
        out = []
        drops = [r for r in raw if r["type"] == "drop"]
        # Many droppers = random world drop (Auction House item), unless they
        # are all in one instance (then it is an instance trash drop).
        if len(drops) > WORLD_DROP_NPCS:
            insts = Counter(self.instance_of_npc(r["id"]) for r in drops)
            inst, n = insts.most_common(1)[0]
            chance = max((max(r["chance"]) for r in drops if r["chance"]), default=None)
            datasets = set().union(*(r["found_in"] for r in drops))
            if inst and n >= len(drops) * 0.8:
                out.append({"type": "instance_trash", "instance": inst, "npcs": len(drops),
                            "chance": chance, "found_in": sorted(datasets)})
            else:
                out.append({"type": "world_drop", "npcs": len(drops), "chance": chance,
                            "found_in": sorted(datasets)})
            raw = [r for r in raw if r["type"] != "drop"]
        for r in raw:
            rec = {"type": r["type"], "id": r["id"], "found_in": sorted(r["found_in"])}
            if r["chance"]:
                rec["chance"] = round(sum(r["chance"]) / len(r["chance"]), 2)
            if r["type"] == "drop":
                info = self.npc_info(r["id"])
                rec.update(name=info["name"], level=info["level"], rank=info["rank"], zone=info["zone"])
                inst = self.instance_of_npc(r["id"])
                if inst:
                    rec["instance"] = inst
                if rec.get("chance") is not None and rec["chance"] < 0.2 and not inst:
                    continue  # tiny open-world chance: not a realistic source
            elif r["type"] == "boss":
                rec.update(name=r["name"], instance=r["instance"])
            elif r["type"] == "vendor":
                info = self.npc_info(r["id"])
                rec.update(name=info["name"], zone=info["zone"], title=info["title"])
                if info["friendly"] in ("A", "H"):
                    rec["faction"] = info["friendly"]
            elif r["type"] == "quest":
                qq = self.q["quest"].get(str(r["id"])) or {}
                cq = self.cm["quests"].get(str(r["id"])) or self.vm["quests"].get(str(r["id"])) or {}
                if not qq and not cq:
                    continue
                rec["name"] = qq.get("name") or cq.get("title")
                rec["level"] = qq.get("questLevel") or cq.get("level")
                rec["min_level"] = qq.get("requiredLevel") or cq.get("min_level") or 1
                fac = faction_of_races(qq.get("requiredRaces") or cq.get("races"))
                if fac:
                    rec["faction"] = fac
                classes = qq.get("requiredClasses") or cq.get("classes")
                if classes:
                    rec["classes_mask"] = classes
                zone = qq.get("zoneOrSort") or cq.get("zone")
                if zone and zone > 0:
                    rec["zone"] = pretty_zone(self.q["zones"].get(str(zone)))
                    if zone in self.area_to_instance:
                        rec["instance"] = self.area_to_instance[zone]
                started = qq.get("startedBy") or []
                starters = (started.get("1") if isinstance(started, dict) else started[:1] and started[0]) or []
                if starters:
                    rec["start_npc"] = self.npc_info(starters[0])["name"]
            elif r["type"] == "object":
                name = (self.cm["objects"].get(str(r["id"])) or self.vm["objects"].get(str(r["id"]))
                        or (self.q["object"].get(str(r["id"])) or {}).get("name"))
                rec["name"] = name
                zone = (self.q["object"].get(str(r["id"])) or {}).get("zoneID")
                if zone:
                    rec["zone"] = pretty_zone(self.q["zones"].get(str(zone)))
                    if int(zone) in self.area_to_instance:
                        rec["instance"] = self.area_to_instance[int(zone)]
            elif r["type"] == "craft":
                rec["skill"] = r.get("skill")
                if r.get("recipe"):
                    rec["recipe"] = r["recipe"]
            elif r["type"] == "container":
                cont = self.blz.get(str(r["id"])) or (self.q["item"].get(str(r["id"])) or {})
                rec["name"] = cont.get("name")
            out.append(rec)
        for rec in out:
            rec["confirmed"] = len(rec["found_in"]) >= 2
        return out

    # ---------- run ----------
    def run(self):
        items, sources = {}, {}
        stat_checks = Counter()
        dropped = Counter()
        for iid, blz in self.blz.items():
            if blz["inventory_type"] not in EQUIP_TYPES or blz["quality"] not in QUALITY:
                dropped["not gear"] += 1
                continue
            known = iid in self.q["item"] or iid in self.cm["items"] or iid in self.vm["items"]
            if not known:
                dropped["not in Era data (e.g. Season of Discovery)"] += 1
                continue
            if self.is_random_suffix(iid, blz):
                dropped["random suffix (no fixed stats)"] += 1
                continue
            srcs = self.sources_for(iid, blz)
            rank = self.honor_rank(iid)
            if rank:
                srcs = [{"type": "pvp_rank", "rank": rank, "found_in": ["CMaNGOS", "VMaNGOS"], "confirmed": True}]
            if not srcs:
                dropped["no known source"] += 1
                continue
            check, notes = self.compare_stats(iid, blz)
            stat_checks[check] += 1
            if notes and check != "confirmed":
                self.conflicts.append(f"- {blz['name']} ({iid}): {' | '.join(notes)}")
            item = {k: v for k, v in blz.items() if v not in (None, [], {}, False)}
            item["quality"] = QUALITY[blz["quality"]]
            item["stats_check"] = check
            items[iid] = item
            sources[iid] = srcs
        write_json(ERA / "items.json", items, compact=True)
        write_json(ERA / "sources.json", sources, compact=True)
        inst_lines = self.instance_report()
        REPORTS.mkdir(exist_ok=True)
        (REPORTS / "instances.md").write_text("\n".join(inst_lines) + "\n", encoding="utf-8")
        src_conf = Counter(s["confirmed"] for v in sources.values() for s in v)
        report = [
            "# Data merge report", "",
            f"Items kept: **{len(items)}**", "",
            "## Items not kept", "", *[f"- {k}: {v}" for k, v in dropped.most_common()], "",
            "## Item stats check (Blizzard Era API vs CMaNGOS / VMaNGOS 1.12)", "",
            "- confirmed: Blizzard matches at least one emulator database",
            "- era-changed: emulators have the item but with other values; the Blizzard (current Era) value is used",
            "- single-source: only Blizzard (and QuestieDB) know the item", "",
            *[f"- {k}: {v}" for k, v in stat_checks.most_common()], "",
            "## Item sources", "",
            f"- confirmed (2+ datasets): {src_conf[True]}",
            f"- single-source: {src_conf[False]}", "",
            f"## Stat differences ({len(self.conflicts)})", "",
            "The site uses the Blizzard value. Listed so a human can spot data errors.", "",
            *sorted(self.conflicts),
        ]
        (REPORTS / "conflicts.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        print(f"items: {len(items)}; dropped: {dict(dropped)}; stats: {dict(stat_checks)}; "
              f"sources confirmed/single: {src_conf[True]}/{src_conf[False]}")


if __name__ == "__main__":
    Merger().run()
