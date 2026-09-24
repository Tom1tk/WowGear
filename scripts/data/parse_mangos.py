"""Parse CMaNGOS / VMaNGOS world database dumps (patch 1.12 emulator data).

Cross-check sources B (CMaNGOS classic-db) and C (VMaNGOS). Both are
community databases for patch 1.12. Era changed some items and loot, so this
data only confirms or questions the Blizzard / QuestieDB values; it is never
the only source for a fact.

Inputs (git-ignored):
  data/raw/cmangos/classicdb.sql  (gunzip of cmangos/classic-db Full_DB/*.sql.gz)
  data/raw/vmangos/world.sql      (7z-extract of brotalnia/database world_full_*.7z)

    python scripts/data/parse_mangos.py
"""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from _common import RAW, STAGING, write_json  # noqa: E402

PATCH_112 = 10  # VMaNGOS patch index for 1.12
TABLES = (
    "item_template", "creature_template", "creature_loot_template",
    "reference_loot_template", "gameobject_loot_template", "item_loot_template",
    "gameobject_template", "quest_template", "npc_vendor", "creature",
)
TUPLE_RE = re.compile(r"\(((?:[^()']|'(?:[^'\\]|\\.)*')*)\)")
FIELD_RE = re.compile(r"\s*'((?:[^'\\]|\\.)*)'|([^,]+)")
INSERT_RE = re.compile(r"INSERT INTO `(\w+)`\s*(\(([^)]*)\))?\s*VALUES", re.I)
CREATE_RE = re.compile(r"CREATE TABLE (?:IF NOT EXISTS )?`(\w+)`")


def _value(quoted, bare):
    if quoted is not None:
        return quoted.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")
    bare = bare.strip()
    if bare.upper() == "NULL":
        return None
    try:
        return int(bare)
    except ValueError:
        try:
            return float(bare)
        except ValueError:
            return bare


def read_tables(path) -> dict[str, list[dict]]:
    tables: dict[str, list[dict]] = defaultdict(list)
    create_cols: dict[str, list[str]] = {}
    current = None
    active = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = CREATE_RE.search(line)
            if m:
                current = m.group(1)
                create_cols[current] = []
                continue
            if current and line.lstrip().startswith("`"):
                create_cols[current].append(line.strip().split("`")[1])
                continue
            if current and ("ENGINE" in line or line.startswith(")")):
                current = None
            m = INSERT_RE.match(line)
            start = 0
            if m:
                table = m.group(1)
                active = None
                if table in TABLES:
                    active = (table, [c.strip().strip("`") for c in m.group(3).split(",")]
                              if m.group(3) else create_cols[table])
                start = m.end()
            if not active:
                continue
            table, cols = active
            for tm in TUPLE_RE.finditer(line, start):
                values = [_value(f.group(1), f.group(2)) for f in FIELD_RE.finditer(tm.group(1))]
                if len(values) == len(cols):
                    tables[table].append(dict(zip(cols, values)))
            if line.rstrip().endswith(";"):
                active = None
    return tables


def lower_keys(rows):
    return [{k.lower(): v for k, v in row.items()} for row in rows]


def latest_patch(rows, key="entry"):
    """VMaNGOS keeps one row per patch; keep the newest row <= 1.12."""
    best = {}
    for row in rows:
        patch = row.get("patch", 0) or 0
        if patch > PATCH_112:
            continue
        cur = best.get(row[key])
        if cur is None or patch >= cur.get("patch", 0):
            best[row[key]] = row
    return list(best.values())


def in_patch(row):
    lo, hi = row.get("patch_min"), row.get("patch_max")
    return (lo is None or lo <= PATCH_112) and (hi is None or hi >= PATCH_112)


def items_from(rows):
    out = {}
    for r in rows:
        stats = {}
        for i in range(1, 11):
            t, v = r.get(f"stat_type{i}"), r.get(f"stat_value{i}")
            if t is not None and v:
                stats[str(t)] = stats.get(str(t), 0) + v
        res = {s: r.get(f"{s}_res", 0) for s in ("holy", "fire", "nature", "frost", "shadow", "arcane")}
        spells = []
        for i in range(1, 6):
            sid = r.get(f"spellid_{i}")
            if sid:
                spells.append([sid, r.get(f"spelltrigger_{i}")])
        out[r["entry"]] = {
            "name": r["name"], "class": r["class"], "subclass": r["subclass"],
            "quality": r["quality"], "inventory_type": r["inventorytype"] if "inventorytype" in r else r.get("inventory_type"),
            "allowable_class": r.get("allowableclass", r.get("allowable_class")),
            "allowable_race": r.get("allowablerace", r.get("allowable_race")),
            "item_level": r.get("itemlevel", r.get("item_level")),
            "required_level": r.get("requiredlevel", r.get("required_level")),
            "required_skill": r.get("requiredskill", r.get("required_skill")),
            "required_reputation": [r.get("requiredreputationfaction", r.get("required_reputation_faction")),
                                    r.get("requiredreputationrank", r.get("required_reputation_rank"))],
            "stats": stats, "armor": r.get("armor"),
            "dmg": [r.get("dmg_min1"), r.get("dmg_max1")], "delay": r.get("delay"),
            "resist": {k: v for k, v in res.items() if v},
            "spells": spells, "bonding": r.get("bonding"),
            "itemset": r.get("itemset") or r.get("set_id"),
            "random_property": r.get("randomproperty", r.get("random_property")),
            "start_quest": r.get("startquest", r.get("start_quest")),
            "honor_rank": r.get("requiredhonorrank", r.get("required_honor_rank")),
        }
    return out


def loot_map(rows):
    by_entry = defaultdict(list)
    for r in rows:
        if in_patch(r):
            by_entry[r["entry"]].append(r)
    return by_entry


def resolve(entry, loot, refs, depth=0, scale=1.0):
    """Yield (item, chance%) for a loot entry, expanding references and
    splitting equal-chance groups (chance 0) evenly."""
    rows = loot.get(entry, [])
    groups = defaultdict(list)
    for r in rows:
        groups[r["groupid"]].append(r)
    for gid, grows in groups.items():
        explicit = sum(abs(r["chanceorquestchance"]) for r in grows if r["chanceorquestchance"])
        zero = [r for r in grows if not r["chanceorquestchance"]]
        share = (max(0.0, 100.0 - explicit) / len(zero)) if (gid and zero) else 100.0
        for r in grows:
            chance = abs(r["chanceorquestchance"]) or share
            chance *= scale
            if r["mincountorref"] < 0 and depth < 4:
                yield from resolve(-r["mincountorref"], refs, refs, depth + 1, chance / 100.0)
            else:
                yield r["item"], chance


def build(path, label):
    print(f"reading {path} ...", flush=True)
    t = {k: lower_keys(v) for k, v in read_tables(path).items()}
    vm = label == "vmangos"
    items = t["item_template"]
    creatures = t["creature_template"]
    quests = t["quest_template"]
    gobs = t["gameobject_template"]
    if vm:
        items, creatures, quests, gobs = (latest_patch(items), latest_patch(creatures),
                                          latest_patch(quests), latest_patch(gobs))
    refs = loot_map(t["reference_loot_template"])
    cloot = loot_map(t["creature_loot_template"])
    gloot = loot_map(t["gameobject_loot_template"])
    iloot = loot_map(t["item_loot_template"])

    npc = {}
    drops = defaultdict(dict)
    for c in creatures:
        cid = c["entry"]
        npc[cid] = {
            "name": c["name"], "min_level": c.get("minlevel", c.get("level_min")),
            "max_level": c.get("maxlevel", c.get("level_max")), "rank": c.get("rank"),
        }
        lid = c.get("lootid", c.get("loot_id"))
        if lid:
            for item, chance in resolve(lid, cloot, refs):
                drops[item][f"npc:{cid}"] = round(drops[item].get(f"npc:{cid}", 0) + chance, 3)
    for g in gobs:
        if g.get("type") == 3 and g.get("data1"):  # chest: data1 = loot id
            for item, chance in resolve(g["data1"], gloot, refs):
                drops[item][f"object:{g['entry']}"] = round(chance, 3)
    for container, _rows in iloot.items():
        for item, chance in resolve(container, iloot, refs):
            drops[item][f"item:{container}"] = round(chance, 3)

    quest_out = {}
    rewards = defaultdict(list)
    for q in quests:
        choice = [q.get(f"rewchoiceitemid{i}") for i in range(1, 7)]
        fixed = [q.get(f"rewitemid{i}") for i in range(1, 5)]
        quest_out[q["entry"]] = {
            "title": q["title"], "min_level": q["minlevel"], "level": q["questlevel"],
            "races": q["requiredraces"], "classes": q["requiredclasses"],
            "zone": q["zoneorsort"],
        }
        for item in [i for i in choice + fixed if i]:
            rewards[item].append(q["entry"])
    vendors = defaultdict(list)
    for v in t["npc_vendor"]:
        vendors[v["item"]].append(v["entry"])
    spawn_maps = defaultdict(set)
    for s in t["creature"]:
        spawn_maps[s["id"]].add(s["map"])
    for cid, maps in spawn_maps.items():
        if cid in npc:
            npc[cid]["maps"] = sorted(maps)

    out = {
        "items": items_from(items), "npc": npc, "quests": quest_out,
        "drops": drops, "quest_rewards": rewards, "vendors": vendors,
        "objects": {g["entry"]: g["name"] for g in gobs},
    }
    write_json(STAGING / f"{label}.json", out, compact=True)
    print(f"{label}: {len(out['items'])} items, {len(npc)} npcs, {len(quest_out)} quests, "
          f"{len(drops)} dropped items", flush=True)


def main():
    build(RAW / "cmangos" / "classicdb.sql", "cmangos")
    build(RAW / "vmangos" / "world.sql", "vmangos")


if __name__ == "__main__":
    main()
