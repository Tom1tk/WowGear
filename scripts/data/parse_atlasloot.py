"""Parse AtlasLootClassic loot tables (dungeons/raids + crafting).

AtlasLootClassic (https://github.com/Hoizame/AtlasLootClassic, GPL-2.0) is a
loot browser addon for Classic. It gives, per instance: the level range, the
bosses with their NPC ids, and the items each boss drops; and per profession:
the craftable items. Used as a second source for boss drops and dungeon
level ranges, and as the main source for crafted items.

    python scripts/data/parse_atlasloot.py
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import RAW, STAGING, write_json  # noqa: E402

AL = RAW / "git" / "AtlasLootClassic"
BLOCK_RE = re.compile(r'^data\["([^"]+)"\] = \{', re.M)
ITEM_RE = re.compile(r"\{\s*\d+,\s*(\d{2,6})\s*[,}]")
NAME_RE = re.compile(r'name = (?:AL|ALIL)\["([^"]+)"\]')
NPC_RE = re.compile(r"npcID = \{?\s*(\d+)")
RANGE_RE = re.compile(r"LevelRange = GetForVersion\(\{(\d+),\s*(\d+),\s*(\d+)\}")
MAP_RE = re.compile(r"MapID = (\d+)")
TYPE_RE = re.compile(r"ContentType = (\w+)")


def blocks(text):
    marks = list(BLOCK_RE.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        yield m.group(1), text[m.end():end]


def parse_instances():
    text = (AL / "AtlasLootClassic_DungeonsAndRaids" / "data.lua").read_text(encoding="utf-8")
    out = {}
    for key, body in blocks(text):
        rng = RANGE_RE.search(body)
        mp = MAP_RE.search(body)
        ctype = TYPE_RE.search(body)
        bosses = []
        current = None
        for line in body.splitlines():
            nm = NAME_RE.search(line)
            if nm and "\t\t\tname" in line and "[NORMAL_DIFF]" not in line:
                current = {"name": nm.group(1), "npc": None, "items": []}
                bosses.append(current)
                continue
            npc = NPC_RE.search(line)
            if npc and current is not None and current["npc"] is None:
                current["npc"] = int(npc.group(1))
            if current is not None:
                current["items"].extend(int(i) for i in ITEM_RE.findall(line))
        out[key] = {
            "map_id": int(mp.group(1)) if mp else None,
            "level_range": [int(x) for x in rng.groups()] if rng else None,
            "content": ctype.group(1) if ctype else None,
            "bosses": [b for b in bosses if b["items"]],
        }
    return out


def parse_crafting():
    text = (AL / "AtlasLootClassic_Crafting" / "data.lua").read_text(encoding="utf-8")
    out = {}
    for prof, body in blocks(text):
        items = {}
        for line in body.splitlines():
            m = re.search(r"\{\s*\d+,\s*(\d{2,6})\s*\}\s*,?\s*--(.*?)(?:/\s*(\d+))?\s*$", line)
            if m:
                items[int(m.group(1))] = m.group(2).strip()
        out[prof] = sorted(items)
    return out


PROFESSIONS = {1: "First Aid", 2: "Blacksmithing", 3: "Leatherworking", 4: "Alchemy",
               6: "Cooking", 8: "Tailoring", 9: "Engineering", 10: "Enchanting"}


def parse_profession_spells():
    """AtlasLoot's PROFESSION_DATA.CLASSIC: spell id -> created item, profession, skill."""
    text = (AL / "AtlasLootClassic" / "Data" / "Profession.lua").read_text(encoding="utf-8")
    start = text.index("PROFESSION_DATA.CLASSIC = {")
    end = text.index("\n}", start)
    out = {}
    for m in re.finditer(r"\[(\d+)\] = \{(\d+),(\d+),(\d+),\d+,\d+,\{([\d,]*)\}", text[start:end]):
        spell, item, prof, skill = (int(x) for x in m.groups()[:4])
        reagents = [int(x) for x in m.group(5).split(",") if x]
        out[spell] = {"item": item, "profession": PROFESSIONS.get(prof, str(prof)), "skill": skill,
                      "reagents": reagents}
    return out


def main():
    inst = parse_instances()
    spells = parse_profession_spells()
    craft = {}
    for prof, spell_ids in parse_crafting().items():
        items = {}
        for sid in spell_ids:
            info = spells.get(sid)
            if info:
                items[info["item"]] = {"spell": sid, "skill": info["skill"], "profession": info["profession"],
                                       "reagents": info["reagents"]}
        craft[prof] = items
    write_json(STAGING / "atlasloot.json", {"instances": inst, "crafting": craft})
    print(f"instances: {len(inst)}, bosses: {sum(len(v['bosses']) for v in inst.values())}, "
          f"crafted items: {sum(len(v) for v in craft.values())}")


if __name__ == "__main__":
    main()
