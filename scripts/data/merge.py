"""Cross-reference warcraftdb, Blizzard and ForeverDB into the data files the build reads.

Inputs (data/forever/staging/, made by parse_warcraftdb.py, parse_blizzard.py, parse_foreverdb.py)
plus hand tables data/forever/instances.json, exclude.json and the ForeverDB boss lists (Loot.lua).
Outputs: data/forever/items.json, sources.json, reports/conflicts.md.

Rules (tasks/forever-plan.md section 2): missing in a source is not a conflict; a field is
confirmed (2+ sources agree), single, or conflict. Scoring value on conflict: Blizzard > warcraftdb >
ForeverDB. Sources ForeverDB labels "k" (Classic data) are ignored.

    python scripts/data/merge.py
"""

from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from _common import FOREVER, REPORTS, STAGING, read_json, write_json  # noqa: E402
from forever_loot import parse_loot  # noqa: E402

EQUIP = {"HEAD", "NECK", "SHOULDER", "CLOAK", "CHEST", "ROBE", "WRIST", "HAND", "WAIST", "LEGS", "FEET",
         "FINGER", "TRINKET", "WEAPON", "TWOHWEAPON", "WEAPONMAINHAND", "WEAPONOFFHAND", "SHIELD",
         "HOLDABLE", "RANGED", "RANGEDRIGHT", "THROWN", "RELIC"}
QUALITY = {"POOR": 0, "COMMON": 1, "UNCOMMON": 2, "RARE": 3, "EPIC": 4, "LEGENDARY": 5}
INV_GROUP = {"WEAPONMAINHAND": "WEAPON", "ROBE": "CHEST", "BODY": "SHIRT"}
STAT_NAME = {"str": "Strength", "agi": "Agility", "sta": "Stamina", "int": "Intellect", "spi": "Spirit",
             "sp": "Spell Power", "ap": "Attack Power", "armor": "Armor", "heal": "Healing"}
# Blizzard "unknown_stats" lines ("SPELL_POWER 12") the parser left unmapped.
BLIZZ_STAT = {"SPELL_POWER": "sp", "SPELL_HEALING_DONE": "heal", "SPELL_DAMAGE_DONE": "sp_damage",
              "CRIT_RATING": "crit_rating", "HIT_RATING": "hit_rating", "DODGE_RATING": "dodge_rating",
              "PARRY_RATING": "parry_rating", "BLOCK_RATING": "block_rating", "HASTE_RATING": "haste_rating",
              "EXPERTISE_RATING": "expertise_rating", "MANA_REGENERATION": "mp5", "HEALTH_REGEN": "hp5",
              "RANGED_ATTACK_POWER": "rap", "BLOCK_VALUE": "block_value", "SPELL_PENETRATION": "spell_pen",
              "BONUS_STAT_FIRE_DAMAGE_DONE": "sp_fire", "BONUS_STAT_FROST_DAMAGE_DONE": "sp_frost",
              "BONUS_STAT_SHADOW_DAMAGE_DONE": "sp_shadow", "BONUS_STAT_ARCANE_DAMAGE_DONE": "sp_arcane",
              "BONUS_STAT_NATURE_DAMAGE_DONE": "sp_nature", "BONUS_STAT_HOLY_DAMAGE_DONE": "sp_holy"}
FOLD = {"hit_rating": "hit", "crit_rating": "crit", "dodge_rating": "dodge", "parry_rating": "parry",
        "block_rating": "block"}
PRIO = ("blizzard", "warcraftdb", "foreverdb")
LABEL = {"blizzard": "Blizzard", "warcraftdb": "warcraftdb", "foreverdb": "ForeverDB"}
FIELDS = ("name", "required_level", "item_level", "inventory_type", "type", "stats", "weapon", "binding", "classes")
EQUIP_ONLY = {"bonus_armor", "sp", "heal", "mp5", "ap", "rap"}
CHANCE_RATIO = 2.0


def stat_text(stats: dict, empty: str = "none") -> str:
    return ", ".join(f"+{v:g} {STAT_NAME.get(k, k)}" for k, v in sorted(stats.items())) or empty


def canon_stats(s: dict) -> dict:
    out: dict = {}
    for k, v in (s or {}).items():
        if v:
            out[FOLD.get(k, k)] = round(out.get(FOLD.get(k, k), 0) + float(v), 1)
    return out


class Merger:
    def __init__(self):
        self.w = read_json(STAGING / "warcraftdb.json")
        self.b = read_json(STAGING / "blizzard.json")
        self.f = read_json(STAGING / "foreverdb.json")
        self.instances = {k: v for k, v in read_json(FOREVER / "instances.json").items() if not k.startswith("_")}
        excl = FOREVER / "exclude.json"
        self.excluded = {k for k in read_json(excl) if not k.startswith("_")} if excl.exists() else set()
        self.loot = parse_loot(self.instances)
        self.zone_inst = {}
        for k, v in self.instances.items():
            for n in [v["name"], (v.get("ids") or {}).get("warcraftdb_zone_name")]:
                if n:
                    self.zone_inst[n.lower()] = k
        self.field_conf = Counter()
        self.pair_conf = Counter()
        self.src_conf = Counter()
        self.examples: list[tuple[str, str, str]] = []  # (field, item, reason)

    # ---------- item fields ----------
    def values(self, iid: str) -> dict:
        """{source: normalized record} for sources that know the item."""
        out = {}
        if iid in self.b:
            rec = dict(self.b[iid])
            stats = dict(rec["stats"])
            for line in rec.get("unknown_stats") or []:
                name, _, num = line.partition(" ")
                if name in BLIZZ_STAT and num.lstrip("-").replace(".", "").isdigit():
                    stats[BLIZZ_STAT[name]] = stats.get(BLIZZ_STAT[name], 0) + float(num)
            rec["stats"] = stats
            out["blizzard"] = rec
        if iid in self.w:
            out["warcraftdb"] = self.w[iid]
        if iid in self.f:
            out["foreverdb"] = {"name": self.f[iid]["name"]}
        return out

    @staticmethod
    def field_value(src: str, rec: dict, field: str):
        if field == "type":
            return None if rec.get("class") is None else (rec["class"], rec.get("subclass"))
        v = rec.get(field)
        if field == "inventory_type" and v:
            return INV_GROUP.get(v, v)
        if field == "name":
            return v.strip().lower() if v else None
        if field == "stats":
            return canon_stats(v) if v is not None else None
        if field == "weapon":
            return None if not v else (round(v["min"]), round(v["max"]), round(v["speed"], 1))
        if field == "required_level":
            return v  # None = unknown, 0 = none: blizzard 0 vs wcdb None is "missing", not a conflict
        return v or None

    def stat_diff(self, vals: dict[str, dict]) -> tuple[bool, str]:
        """Compare stat dicts of the sources; unparsed effects / rating wording are not conflicts."""
        names = list(vals)
        for i, a in enumerate(names):
            for c in names[i + 1:]:
                sa, sc = vals[a][0], vals[c][0]
                diff = []
                if not sa or not sc:
                    continue  # one source has no parsed stat block: nothing to compare
                for k in sorted(set(sa) | set(sc)):
                    x, y = sa.get(k), sc.get(k)
                    if x == y or (None in (x, y) and k in EQUIP_ONLY):  # Equip-effect bonuses Blizzard omits: missing, not a conflict
                        continue
                    if (x is None and vals[c][1]) or (y is None and vals[a][1]):
                        continue  # the other source has effect text its parser did not read
                    diff.append(k)
                if diff:
                    return True, (f"Stats differ: {LABEL[a]} {stat_text({k: sa[k] for k in diff if k in sa}, "none of these")}, "
                                  f"{LABEL[c]} {stat_text({k: sc[k] for k in diff if k in sc}, "none of these")}")
        return False, ""

    def build_item(self, iid: str, recs: dict) -> dict:
        checks, uncertain, conflicts = {}, [], {}
        for field in FIELDS:
            vals = {}
            for src, rec in recs.items():
                v = self.field_value(src, rec, field)
                if v is None or (field == "required_level" and v == 0 and src == "blizzard" and
                                 recs.get("warcraftdb", {}).get("required_level") is None):
                    continue
                vals[src] = (v, bool(rec.get("unparsed_effects"))) if field == "stats" else v
            if len(vals) < 2:
                if vals:
                    checks[field] = "single"
                continue
            if field == "stats":
                bad, reason = self.stat_diff(vals)
                if bad and "block_value" in reason:
                    reason += " (the Blizzard block figure looks like a different field; warcraftdb's is used for scoring)"
            else:
                distinct = {repr(v) for v in vals.values()}
                bad = len(distinct) > 1
                reason = ""
                if bad:
                    reason = (f"{field.replace('_', ' ').capitalize()} differs: " +
                              "; ".join(f"{LABEL[s]} {v}" for s, v in vals.items()))
            if bad:
                checks[field] = "conflict"
                uncertain.append(reason)
                conflicts[field] = {s: (v[0] if field == "stats" else v) for s, v in vals.items()}
                self.field_conf[field] += 1
                names = list(vals)
                for i, a in enumerate(names):
                    for c in names[i + 1:]:
                        self.pair_conf[f"{LABEL[a]} vs {LABEL[c]}"] += 1
                self.examples.append((field, iid, reason))
            else:
                checks[field] = "confirmed"
        base = recs.get("blizzard") or recs.get("warcraftdb")
        item = {k: base.get(k) for k in ("name", "item_level", "required_level", "inventory_type", "class", "subclass",
                                        "binding", "unique", "classes", "races", "skill", "reputation", "effects",
                                        "unparsed_effects", "weapon")}
        item["quality"] = QUALITY.get(base.get("quality"), 1)
        stats = dict(base.get("stats") or {})
        wc = recs.get("warcraftdb")
        if wc and recs.get("blizzard") and recs["blizzard"].get("unparsed_effects"):
            for k, v in wc["stats"].items():  # effect text Blizzard's parser could not read
                stats.setdefault(k, v)
        stats.pop("block_value", None)  # Blizzard shield_block is not the in-game block value: warcraftdb only
        if wc and wc["stats"].get("block_value"):
            stats["block_value"] = wc["stats"]["block_value"]
        item["stats"] = stats
        if item["required_level"] is None:
            item["required_level"] = (wc or {}).get("required_level") or 0
        item.update(uncertain=uncertain, checks=checks, found_in=sorted(recs), conflict_values=conflicts)
        return {k: v for k, v in item.items() if v not in (None, [], {}) or k in ("uncertain", "checks")}

    # ---------- sources ----------
    def inst_of_boss(self, npc, name: str) -> tuple[str | None, str | None]:
        if npc and int(npc) in self.loot["npc"]:
            return self.loot["npc"][int(npc)], None
        key = self.loot["boss"].get((name or "").lower())
        return (key, "matched by boss name") if key else (None, None)

    def sources_for(self, iid: str) -> list[dict]:
        found: dict[tuple, dict] = {}

        def add(src, kind, key, **kw):
            rec = found.setdefault((kind, key), {"type": kind, "found_in": set(), "chance_by": {}})
            rec["found_in"].add(src)
            ch = kw.pop("chance", None)
            if ch:
                rec["chance_by"][src] = float(ch)
            for k, v in kw.items():
                if v not in (None, "") and k not in rec:
                    rec[k] = v

        for s in (self.w.get(iid) or {}).get("sources", []):
            t = s["type"]
            if t == "drop":
                inst, via = self.inst_of_boss(s["id"], s["name"])
                add("warcraftdb", "drop", (s["name"] or "").lower(), id=s["id"], name=s["name"],
                    chance=s.get("chance"), instance=inst, instance_via=via)
            elif t in ("object", "item"):
                add("warcraftdb", "object" if t == "object" else "container", (s["name"] or "").lower(),
                    id=s["id"], name=s["name"], chance=s.get("chance"))
            elif t == "quest":
                add("warcraftdb", "quest", s["id"], id=s["id"], name=s["name"], zone=s.get("zone"),
                    instance=self.zone_inst.get((s.get("zone") or "").lower()))
            elif t == "vendor":
                add("warcraftdb", "vendor", s["id"], id=s["id"], name=s["name"], zone=s.get("zone"),
                    faction=s.get("faction"))
            elif t == "craft":
                add("warcraftdb", "craft", s["id"], id=s["id"], name=s["name"])
        fe = self.f.get(iid)
        d_inst = None
        for p in (fe or {}).get("sources", []):
            if len(p) < 2 or p[-1] in ("k", "c"):
                continue  # k = Classic data; c = unconfirmed client clue
            g = p[0]
            side = {"a": "A", "h": "H"}.get(p[4] if g == "q" and len(p) > 4 else p[3] if g == "V" and len(p) > 3 else "")
            if g == "d":
                key = self.loot["boss"].get(p[2].lower()) or self.loot["inst"].get(int(p[1]))
                d_inst = key or d_inst
                if p[2]:
                    add("foreverdb", "drop", p[2].lower(), name=p[2], chance=p[3], instance=key)
            elif g == "m":  # a mob (npc id) in the dungeon the "d" row names
                add("foreverdb", "drop", p[2].lower(), id=int(p[1]), name=p[2],
                    instance=self.loot["npc"].get(int(p[1])) or d_inst)
            elif g == "R":
                add("foreverdb", "drop", p[2].lower(), id=int(p[1]), name=p[2])
            elif g == "q":
                add("foreverdb", "quest", int(p[1]), id=int(p[1]), name=p[2], faction=side,
                    level=int(p[3]) if p[3].isdigit() else None)
            elif g == "V":
                add("foreverdb", "vendor", int(p[1]), id=int(p[1]), faction=side, copper=p[2])
            elif g == "c":
                add("foreverdb", "craft", int(p[3]) if p[3].isdigit() else p[1], name=p[1], skill=p[2])
            elif g == "r":
                add("foreverdb", "vendor", f"rep:{p[1]}", name=p[3], reputation={"faction_id": p[1], "standing": p[2]})
            elif g == "o":
                add("foreverdb", "object", p[1].lower(), name=p[1], chance=p[2])
            elif g == "x":
                add("foreverdb", "container", p[2].lower(), id=int(p[1]), name=p[2])
        out = []
        for (kind, _key), r in found.items():
            r["found_in"] = sorted(r["found_in"])
            r["confirmed"] = len(r["found_in"]) >= 2
            r["conflict"] = False
            ch = r.pop("chance_by")
            if ch:
                r["chance"] = round(ch.get("warcraftdb", ch.get("foreverdb")), 2)
                if len(ch) == 2 and min(ch.values()) > 0 and max(ch.values()) / min(ch.values()) > CHANCE_RATIO:
                    r["conflict"] = True
                    r["conflict_reason"] = (f"Drop chance for {r.get('name')}: warcraftdb {ch['warcraftdb']:g}%, "
                                            f"ForeverDB {ch['foreverdb']:g}% (more than 2x apart).")
            out.append(r)
        self.disjoint_conflicts(out)
        for r in out:
            if r["type"] == "drop" and not r.get("instance") and r["found_in"] == ["warcraftdb"]:
                r["uncertain"] = (f"warcraftdb lists '{r.get('name')}' as a dropper, but no source gives its zone or "
                                  "level or places it in an instance, so it is treated as an open-world drop.")
            elif r.get("instance_via"):
                r["uncertain"] = (f"Placed in {self.instances[r['instance']]['name']} by boss name only: "
                                  "no source maps this NPC id to the instance.")
            r.pop("instance_via", None)
            if r["conflict"]:
                self.src_conf[r["type"]] += 1
            if r.get("instance") is None:
                r.pop("instance", None)
        return out

    def disjoint_conflicts(self, out: list[dict]) -> None:
        """Both sources list this kind of source for the item but not one in common."""
        for kind in ("drop", "quest"):  # vendor lists are partial in ForeverDB (first vendor only)
            rows = [r for r in out if r["type"] == kind]
            by = {s: [r for r in rows if s in r["found_in"]] for s in ("warcraftdb", "foreverdb")}
            placed = kind != "drop" or any(r.get("instance") for r in rows)  # trash lists are partial on both sides
            if placed and by["warcraftdb"] and by["foreverdb"] and not any(r["confirmed"] for r in rows):
                def names(rs):
                    return ", ".join(sorted({str(r.get("name") or f"NPC {r.get('id')}") for r in rs})[:3])
                reason = (f"warcraftdb lists {kind} source {names(by['warcraftdb'])}; "
                          f"ForeverDB lists {kind} source {names(by['foreverdb'])}; no overlap.")
                for r in rows:
                    r["conflict"], r["conflict_reason"] = True, reason

    # ---------- run ----------
    def run(self):
        items, sources, dropped = {}, {}, Counter()
        for iid in sorted(set(self.w) | set(self.b), key=int):
            recs = self.values(iid)
            base = recs.get("blizzard") or recs["warcraftdb"]
            if base["class"] not in (2, 4) or base["inventory_type"] not in EQUIP:
                dropped["not equippable gear"] += 1
            elif QUALITY.get(base["quality"], 0) < 1:
                dropped["poor quality"] += 1
            elif base.get("temporary") or iid in self.excluded:
                dropped["temporary or excluded by hand"] += 1
            elif (base.get("required_level") or 0) > 60:
                dropped["required level above 60"] += 1
            else:
                srcs = self.sources_for(iid)
                if not srcs:
                    dropped["no known source"] += 1
                    continue
                items[iid] = self.build_item(iid, recs)
                sources[iid] = srcs
        for iid in self.f:
            if iid not in self.w and iid not in self.b:
                dropped["ForeverDB only (no stats from Blizzard/warcraftdb yet)"] += 1
        write_json(FOREVER / "items.json", items, compact=True)
        write_json(FOREVER / "sources.json", sources, compact=True)
        self.report(items, sources, dropped)

    def report(self, items, sources, dropped):
        n_unc = sum(1 for i in items.values() if i["uncertain"])
        srcs = [s for v in sources.values() for s in v]
        lines = ["# Cross-reference report (warcraftdb / Blizzard / ForeverDB)", "",
                 f"Items kept: **{len(items)}**; with at least one conflict (Uncertain): **{n_unc}**.",
                 f"Items known to both warcraftdb and Blizzard: "
                 f"{sum(1 for i in items.values() if {'blizzard', 'warcraftdb'} <= set(i['found_in']))}.",
                 f"Source entries: {len(srcs)}; confirmed by 2 datasets: {sum(s['confirmed'] for s in srcs)}; "
                 f"conflicts: {sum(s['conflict'] for s in srcs)}.", "",
                 "Missing in a source is not a conflict. ForeverDB sources labelled Classic (k) or clue (c) are ignored.",
                 "Value used for scoring on conflict: Blizzard > warcraftdb > ForeverDB.", "",
                 "## Items not kept", "", *[f"- {k}: {v}" for k, v in dropped.most_common()], "",
                 "## Item field conflicts by field", "",
                 *[f"- {k}: {v}" for k, v in self.field_conf.most_common()], "",
                 "## By source pair", "", *[f"- {k}: {v}" for k, v in self.pair_conf.most_common()], "",
                 "## Source conflicts by kind", "", *[f"- {k}: {v}" for k, v in self.src_conf.most_common()], "",
                 "## Examples (first 50 item conflicts)", ""]
        for field, iid, reason in self.examples[:50]:
            lines.append(f"- {items[iid]['name']} ({iid}) [{field}]: {reason}")
        ex = list({(iid, s["conflict_reason"]): (iid, s) for iid, v in sources.items() for s in v if s["conflict"]}.values())[:25]
        lines += ["", "## Examples (source conflicts)", ""]
        lines += [f"- {items[i]['name']} ({i}): {s['conflict_reason']}" for i, s in ex]
        REPORTS.mkdir(exist_ok=True)
        (REPORTS / "conflicts.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"items {len(items)}, uncertain {n_unc}, dropped {dict(dropped)}, field conflicts {dict(self.field_conf)}, "
              f"source conflicts {dict(self.src_conf)}")


if __name__ == "__main__":
    Merger().run()
