"""ForeverDB Loot.lua -> which instance each boss belongs to (npc id / boss name -> instances.json key).

Only the boss lists are used (to place drops); loot lines labelled "c" (Classic data) are never read.
Multi-wing dungeons that ForeverDB lists as one entry (Scarlet Monastery, Dire Maul, Blackrock Spire)
are split by boss name with the hand tables below.
"""

from __future__ import annotations

import re

from _common import RAW

WINGS = {
    "scarlet monastery": ("sm_graveyard", {
        "sm_library": ["Houndmaster Loksey", "Arcanist Doan"],
        "sm_armory": ["Herod"],
        "sm_cathedral": ["High Inquisitor Fairbanks", "Scarlet Commander Mograine", "High Inquisitor Whitemane"]}),
    "dire maul": (None, {
        "dire_maul_east": ["Pusillin", "Zevrim Thornhoof", "Hydrospawn", "Lethtendris", "Alzzin the Wildshaper"],
        "dire_maul_west": ["Tendris Warpwood", "Illyanna Ravenoak", "Magister Kalendris", "Immol'thar",
                           "Prince Tortheldrin"],
        "dire_maul_north": ["Guard Mol'dar", "Stomper Kreeg", "Guard Fengus", "Guard Slip'kik", "Captain Kromcrush",
                            "Cho'Rush the Observer", "King Gordok"]}),
    "blackrock spire": ("lower_blackrock_spire", {
        "upper_blackrock_spire": ["Pyroguard Emberseer", "Solakar Flamewreath", "Jed Runewatcher", "Goraluk Anvilcrack",
                                  "Warchief Rend Blackhand", "The Beast", "General Drakkisath", "Lord Valthalak"]}),
}
ALIASES = {"stormwind stockade": "the stockade", "sunken temple": "the temple of atal'hakkar (sunken temple)",
           "deadmines": "the deadmines", "the hall of thanes": "hall of thanes"}


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name.lower().strip())


def parse_loot(instances: dict) -> dict:
    """-> {"inst": {id: key-or-None}, "npc": {npc: key}, "boss": {lower name: key}}"""
    text = (RAW / "foreverdb" / "Loot.lua").read_text(encoding="utf-8")
    by_name = {_norm(v["name"]): k for k, v in instances.items()}
    wing_of = {_norm(b): k for _d, wings in WINGS.values() for k, bosses in wings.items() for b in bosses}
    out = {"inst": {}, "npc": {}, "boss": {}, "names": {}}
    head = re.compile(r'\{ id = (\d+), name = "([^"]*)", kind = "(\w+)"')
    boss = re.compile(r'\{ npc = (\d+), name = "([^"]*)"')
    cur = None
    for line in text.split("\n"):
        h = head.search(line)
        if h:
            name = _norm(h.group(2))
            key = by_name.get(ALIASES.get(name, name))
            cur = (int(h.group(1)), name, key)
            out["inst"][cur[0]] = key if name not in WINGS else None
            out["names"][cur[0]] = h.group(2)
            continue
        b = boss.search(line)
        if b and cur:
            default = WINGS[cur[1]][0] if cur[1] in WINGS else cur[2]
            key = wing_of.get(_norm(b.group(2)), default) if cur[1] in WINGS else cur[2]
            if key:
                out["npc"][int(b.group(1))] = key
                out["boss"][_norm(b.group(2))] = key
    return out
