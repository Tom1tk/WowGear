"""Normalize cached forever.warcraftdb.com responses into staging/warcraftdb.json.

Reads data/raw/warcraftdb/{node,tooltip,tab}/ (see fetch_warcraftdb.py). The tooltip
HTML is turned into text lines and each line is classified by regex (the
data-line-type attribute is not reliable: "captured-*" types hold anything).
Every "Equip:" / "Use:" / "Chance on hit:" line is kept verbatim in `effects`;
those no pattern understood are repeated in `unparsed_effects`; any other line we
could not classify goes to `unknown_lines`. Nothing is dropped silently.

Stat keys follow parse_blizzard.py (str agi sta int spi armor sp heal hit crit
spell_hit spell_crit ap rap hp5 mp5 def dodge parry block block_value res_* sp_<school>
wskill_*). Keys that only exist because Forever words things differently:
  sp_damage      "Increases damage done by magical spells ... by up to N" (damage only)
  <x>_rating     "Increases your hit/critical strike/dodge/parry/... by N" (flat number,
                 no % sign; whether it is a rating or percentage points is unconfirmed)

    python scripts/data/parse_warcraftdb.py
"""

from __future__ import annotations

import html
import json
import os
import re
import sys

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(__file__))
from _common import RAW, STAGING, write_json  # noqa: E402

DIR = RAW / "warcraftdb"
QUALITY = {"Poor": "POOR", "Common": "COMMON", "Uncommon": "UNCOMMON", "Rare": "RARE",
           "Epic": "EPIC", "Legendary": "LEGENDARY", "Artifact": "ARTIFACT"}
CLASS_IDS = {"Warrior": 1, "Paladin": 2, "Hunter": 3, "Rogue": 4, "Priest": 5, "Shaman": 7,
             "Mage": 8, "Warlock": 9, "Druid": 11}
# Skyborne ids 95 (High Order, Alliance) / 96 (Windshaper, Horde) per Blizzard.
RACE_IDS = {"Human": 1, "Orc": 2, "Dwarf": 3, "Night Elf": 4, "Undead": 5, "Tauren": 6, "Gnome": 7,
            "Troll": 8, "Skyborne (Alliance)": 95, "Skyborne (Horde)": 96,
            "High Order": 95, "Windshaper": 96}
SLOTS = {"Head": "HEAD", "Neck": "NECK", "Shoulder": "SHOULDER", "Back": "CLOAK", "Chest": "CHEST",
         "Shirt": "SHIRT", "Tabard": "TABARD", "Wrist": "WRIST", "Hands": "HAND", "Waist": "WAIST",
         "Legs": "LEGS", "Feet": "FEET", "Finger": "FINGER", "Trinket": "TRINKET",
         "One-Hand": "WEAPON", "Two-Hand": "TWOHWEAPON", "Main Hand": "WEAPONMAINHAND",
         "Off Hand": "WEAPONOFFHAND", "Held In Off-hand": "HOLDABLE", "Held In Off-Hand": "HOLDABLE",
         "Ranged": "RANGED", "Thrown": "THROWN", "Relic": "RELIC", "Ranged Right": "RANGEDRIGHT"}
ARMOR_SUB = {"Miscellaneous": 0, "Cloth": 1, "Leather": 2, "Mail": 3, "Plate": 4, "Cosmetic": 5,
             "Shield": 6, "Libram": 7, "Idol": 8, "Totem": 9}
WEAPON_SUB = {"Axe": 0, "Bow": 2, "Gun": 3, "Mace": 4, "Polearm": 6, "Sword": 7, "Staff": 10,
              "Fist Weapon": 13, "Miscellaneous": 14, "Dagger": 15, "Thrown": 16, "Crossbow": 18,
              "Wand": 19, "Fishing Pole": 20}
TWO_HAND = {"Axe": 1, "Mace": 5, "Sword": 8}  # same type name as the one-hander; slot tells
BINDING = {"picked up": "ON_ACQUIRE", "equipped": "ON_EQUIP", "used": "ON_USE"}
PRIMARY = {"Strength": "str", "Agility": "agi", "Stamina": "sta", "Intellect": "int", "Spirit": "spi"}
SCHOOLS = ("Fire", "Nature", "Frost", "Shadow", "Arcane", "Holy")
RATING_NAMES = {"hit": "hit", "critical strike": "crit", "dodge": "dodge", "parry": "parry",
                "block": "block", "spell hit": "spell_hit", "spell critical strike": "spell_crit",
                "haste": "haste", "spell haste": "spell_haste", "expertise": "expertise",
                "resilience": "resilience", "armor penetration": "armor_pen"}

N = r"(\d+(?:\.\d+)?)"
# (regex on the text after "Equip: ", stat key(s)); first match wins.
EQUIP = [
    (rf"^Increases damage and healing done by magical spells and effects by up to {N}\.?$", ("sp",)),
    (rf"^Increases spell power by {N}\.?$", ("sp",)),
    (rf"^Increases healing done by (?:magical )?spells and effects by up to {N}\.?$", ("heal",)),
    (rf"^Increases healing done by up to {N}\.?$", ("heal",)),
    (rf"^Increases damage done by magical spells and effects by up to {N}\.?$", ("sp_damage",)),
    (rf"^Increases healing done by up to {N} and damage done by up to {N} for all magical spells and effects\.?$",
     ("heal", "sp_damage")),
    (rf"^Improves your chance to get a critical strike with spells by {N}%\.?$", ("spell_crit",)),
    (rf"^Improves your chance to get a critical strike by {N}%\.?$", ("crit",)),
    (rf"^Improves your chance to hit with spells by {N}%\.?$", ("spell_hit",)),
    (rf"^Improves your chance to hit by {N}%\.?$", ("hit",)),
    (rf"^Restores {N} mana per 5 sec\.?$", ("mp5",)),
    (rf"^Restores {N} health per 5 sec\.?$", ("hp5",)),
    (rf"^Increases attack power by {N}\.?$", ("ap",)),
    (rf"^\+{N} Attack Power\.?$", ("ap",)),
    (rf"^\+{N} ranged Attack Power\.?$", ("rap",)),
    (rf"^Increases ranged attack power by {N}\.?$", ("rap",)),
    (rf"^\+{N} Attack Power in Cat, Bear, and Dire Bear forms only\.?$", ("feral_ap",)),
    (rf"^Increased Defense \+{N}\.?$", ("def",)),
    (rf"^Increases defense skill by {N}\.?$", ("def",)),
    (rf"^Increases your armor by {N}\.?$", ("bonus_armor",)),
    (rf"^Increases your chance to dodge an attack by {N}%\.?$", ("dodge",)),
    (rf"^Increases your chance to parry an attack by {N}%\.?$", ("parry",)),
    (rf"^Increases your chance to block attacks with a shield by {N}%\.?$", ("block",)),
    (rf"^Increases the block value of your shield by {N}\.?$", ("block_value",)),
    (rf"^Decreases the magical resistances of your spell targets by {N}\.?$", ("spell_pen",)),
]
_SCHOOL_RE = re.compile(rf"^Increases damage done by (\w+) spells and effects by up to {N}\.?$")
_RATING_RE = re.compile(rf"^Increases your ([a-z ]+?) by {N}\.?$")
_WSKILL_RE = re.compile(rf"^Increased (Daggers|Swords|Maces|Axes|Bows|Guns|Crossbows|Two-handed Swords|"
                        rf"Two-handed Maces|Two-handed Axes|Staves|Polearms|Fist Weapons|Unarmed) \+{N}\.?$", re.I)
EQUIP_RX = [(re.compile(p), keys) for p, keys in EQUIP]
EFFECT_PREFIX = re.compile(r"^(Equip|Use|Chance on hit|Chance on melee attack|Chance on ranged hit)\b", re.I)
IGNORED = [re.compile(p) for p in (
    r"^Durability \d+ / \d+$", r"^Sell Price", r"^Max Stack:", r"^\(\d+(?:\.\d+)? damage per second\)$",
    r"^You haven't collected this appearance", r'^".*"$', r"^$", r"^Unique-Equipped$", r"^Conjured Item$",
    r"^Quest Item$", r"^Soulbound$", r"^Heroic$", r"^Item Level \d+$",
)]


def num(text: str) -> float:
    return float(text.replace(",", ""))


def tooltip_lines(markup: str) -> tuple[dict, list[tuple[str, str, str]]]:
    """-> (title info, [(line_type, text, text_of_second_span_or_'')])."""
    soup = BeautifulSoup(markup, "html.parser")
    title, lines = {}, []
    for el in soup.find_all(["tt-title", "tt-line", "tt-double-line"]):
        if el.name == "tt-title":
            title = {"name": el.get_text(strip=True), "quality": el.get("data-quality")}
        elif el.name == "tt-double-line":
            spans = el.find_all("span", recursive=False)
            left = spans[0].get_text(" ", strip=True) if spans else el.get_text(" ", strip=True)
            right = spans[1].get_text(" ", strip=True) if len(spans) > 1 else ""
            lines.append(("double", html.unescape(left), html.unescape(right)))
        elif el.find_parent("tt-double-line") is None:
            lines.append((el.get("data-line-type") or "", html.unescape(el.get_text("")), ""))  # raw: set pieces are indented
    return title, lines


def add(stats: dict, key: str, value: float) -> None:
    stats[key] = round(stats.get(key, 0) + value, 4)


def parse_equip(body: str, stats: dict) -> bool:
    """Add the stat(s) an 'Equip:' body gives to stats; False if no pattern knows it."""
    body = body.strip()
    for rx, keys in EQUIP_RX:
        m = rx.match(body)
        if m:
            for key, val in zip(keys, m.groups()):
                add(stats, key, num(val))
            return True
    m = _SCHOOL_RE.match(body)
    if m and m.group(1).title() in SCHOOLS:
        add(stats, f"sp_{m.group(1).lower()}", num(m.group(2)))
        return True
    m = _RATING_RE.match(body)
    if m and m.group(1) in RATING_NAMES:
        add(stats, f"{RATING_NAMES[m.group(1)]}_rating", num(m.group(2)))
        return True
    m = _WSKILL_RE.match(body)
    if m:
        skill = m.group(1).lower().replace("two-handed ", "2h_").replace(" ", "_")
        add(stats, f"wskill_{skill}", num(m.group(2)))
        return True
    return False


def subclass_id(cls: int | None, name: str | None, slot: str | None) -> int | None:
    if not name:
        return None
    if cls == 4:
        return ARMOR_SUB.get(name)
    if cls == 2:
        base = re.sub(r"^(Two-Handed|Two-Hand|One-Handed|One-Hand)\s+", "", name).rstrip("s")
        if slot == "TWOHWEAPON" and base in TWO_HAND:
            return TWO_HAND[base]
        return WEAPON_SUB.get(base, WEAPON_SUB.get(name))
    return None


def parse_tooltip(markup: str) -> dict:
    """Tooltip HTML -> normalized fields (no node / source data)."""
    title, lines = tooltip_lines(markup)
    out = {"name": title.get("name"), "stats": {}, "effects": [], "unparsed_effects": [],
           "unknown_lines": [], "inventory_type": None, "type_name": None, "binding": None,
           "unique": False, "weapon": None, "classes": None, "races": None, "reputation": None,
           "skill": None, "set": None, "item_level": None, "required_level": None}
    stats = out["stats"]
    for ltype, raw, right in lines:
        text = raw.strip()
        indented = raw[:1].isspace() and bool(text)
        if (ltype.startswith("set-") or re.match(r"^\(\d+\) Set:", text) or re.match(r"^.+ \(\d+/\d+\)$", text)
                or (indented and out["set"] is not None)):
            m = re.match(r"^\((\d+)\) Set:\s*(.*)$", text)
            if m:
                if out["set"]:
                    out["set"]["bonuses"].append({"pieces": int(m.group(1)), "text": m.group(2)})
            elif ltype == "set-name" or re.match(r"^.+ \(\d+/\d+\)$", text):
                n = re.match(r"^(.+?) \((\d+)/(\d+)\)$", text)
                out["set"] = {"name": n.group(1) if n else text, "size": int(n.group(3)) if n else None,
                              "pieces": [], "bonuses": []}
            elif out["set"] is not None and text:
                out["set"]["pieces"].append(text)
            continue
        if ltype == "double":
            if text in SLOTS:
                out["inventory_type"], out["type_name"] = SLOTS[text], right or None
                continue
            m = re.match(r"^(\d+) - (\d+) Damage$", text)
            sp = re.match(r"^Speed (\d+(?:\.\d+)?)$", right)
            if m and sp:
                lo, hi, speed = int(m.group(1)), int(m.group(2)), float(sp.group(1))
                out["weapon"] = {"min": lo, "max": hi, "speed": speed,
                                 "dps": round((lo + hi) / 2 / speed, 2) if speed else 0}
                continue
            out["unknown_lines"].append(f"{text} | {right}")
            continue
        if text in SLOTS:  # single-span slot line (Shirt, Finger, Trinket, Held In Off-hand ...)
            out["inventory_type"] = SLOTS[text]
            continue
        if (m := re.match(r"^Item Level (\d+)$", text)):
            out["item_level"] = int(m.group(1))
        elif (m := re.match(r"^Binds (?:when|to) ?(picked up|equipped|used|account)", text)):
            out["binding"] = BINDING.get(m.group(1), "BOA" if m.group(1) == "account" else None)
        elif re.match(r"^Unique", text):
            out["unique"] = True
        elif (m := re.match(r"^Requires Level (\d+)", text)):
            out["required_level"] = int(m.group(1))
        elif (m := re.match(r"^Classes:\s*(.+)$", text)):
            names = [n.strip() for n in m.group(1).split(",")]
            ids = [CLASS_IDS[n] for n in names if n in CLASS_IDS]
            out["classes"] = ids
            if len(ids) != len(names):
                out["unknown_lines"].append(text)
        elif (m := re.match(r"^Races:\s*(.+)$", text)):
            names = [n.strip() for n in m.group(1).split(",")]
            out["races"] = [RACE_IDS[n] for n in names if n in RACE_IDS]
            if len(out["races"]) != len(names):
                out["unknown_lines"].append(text)
        elif (m := re.match(r"^Requires (.+?) - (Hated|Hostile|Unfriendly|Neutral|Friendly|Honored|Revered|Exalted)$", text)):
            out["reputation"] = {"faction": m.group(1), "level": m.group(2)}
        elif (m := re.match(r"^Requires ([A-Za-z' ]+?) \((\d+)\)$", text)):
            out["skill"] = {"name": m.group(1), "level": int(m.group(2))}
        elif (m := re.match(r"^([\d,]+) Armor$", text)):
            add(stats, "armor", num(m.group(1)))
        elif (m := re.match(r"^\+([\d,]+) Armor$", text)):
            add(stats, "armor", num(m.group(1)))
        elif (m := re.match(r"^([\d,]+) Block$", text)):
            add(stats, "block_value", num(m.group(1)))
        elif (m := re.match(r"^([+-])(\d+) (Strength|Agility|Stamina|Intellect|Spirit)$", text)):
            add(stats, PRIMARY[m.group(3)], int(m.group(2)) * (1 if m.group(1) == "+" else -1))
        elif (m := re.match(r"^\+(\d+) (Fire|Nature|Frost|Shadow|Arcane|Holy) Resistance$", text)):
            add(stats, f"res_{m.group(2).lower()}", int(m.group(1)))
        elif (m := re.match(r"^\+(\d+) (?:to )?All Resistances$", text)):
            for s in SCHOOLS[:5]:
                add(stats, f"res_{s.lower()}", int(m.group(1)))
        elif EFFECT_PREFIX.match(text):
            out["effects"].append(text)
            m = re.match(r"^Equip:\s*(.*)$", text, re.S)
            if m:
                if not parse_equip(m.group(1), stats):
                    out["unparsed_effects"].append(text)
            else:
                out["unparsed_effects"].append(text)
        elif (m := re.match(r"^\+?(\d+) - (\d+) (\w+) Damage$", text)):
            out["effects"].append(text)  # bonus elemental weapon damage: kept raw
            out["unparsed_effects"].append(text)
        elif any(rx.match(text) for rx in IGNORED):
            pass
        elif ltype == "captured-blank":
            pass
        else:
            out["unknown_lines"].append(text)
    return out


def strip_html(text: str | None) -> str | None:
    return re.sub(r"<[^>]+>", "", text).strip() if text else None


def parse_tab(slug: str, rows: list[dict]) -> list[dict]:
    """Tab rows -> source entries ({type, id, name, ...})."""
    out = []
    for r in rows:
        if slug == "dropped-by":
            kind = (r.get("source_kind_label") or "").lower()
            typ = {"npc": "drop", "object": "object", "gameobject": "object", "item": "item"}.get(kind, kind or "drop")
            out.append({"type": typ, "id": r.get("source_id"), "name": r.get("name"),
                        "chance": r.get("chance"), "loot_type": r.get("loot_type_label"),
                        "quantity": r.get("quantity")})
        elif slug == "reward-from":
            out.append({"type": "quest", "id": r.get("id"), "name": r.get("name"),
                        "zone": r.get("zone"), "zone_id": r.get("zone_id"),
                        "choice": (r.get("reward_type") or "").lower() == "choice",
                        "reward_type": r.get("reward_type")})
        elif slug == "sold-by":
            zone = re.search(r'/data/zone/(\d+)', r.get("location") or "")
            react = r.get("reaction") or ""
            side = "H" if "faction-horde" in react else "A" if "faction-alliance" in react else None
            out.append({"type": "vendor", "id": r.get("npc_id"), "name": r.get("name"),
                        "zone": strip_html(r.get("location")), "zone_id": int(zone.group(1)) if zone else None,
                        "cost": r.get("cost"), "faction": side, "reaction": strip_html(react)})
        elif slug == "created-by":
            out.append({"type": "craft", "id": r.get("ID"), "name": r.get("name"), "reagents": r.get("reagents")})
        else:  # contained-in, fished-in, ... : keep what identifies the row
            out.append({"type": slug, "id": r.get("id") or r.get("ID") or r.get("source_id") or r.get("npc_id"),
                        "name": r.get("name"), "row": {k: v for k, v in r.items() if k not in ("icon", "color")}})
    return out


def load_tabs(item_id: int) -> list[dict]:
    sources = []
    tab_dir = DIR / "tab" / str(item_id)
    if not tab_dir.is_dir():
        return sources
    for path in sorted(tab_dir.glob("*_*.json")):
        slug = path.stem.rsplit("_", 1)[0]
        data = json.loads(path.read_text(encoding="utf-8"))
        sources += parse_tab(slug, data.get("rows") or [])
    return sources


def normalize(node: dict, tooltip: dict, sources: list[dict]) -> dict:
    d = node.get("data") or {}
    tt = parse_tooltip(tooltip.get("html", ""))
    cls = {"Weapon": 2, "Armor": 4}.get(d.get("item_class"))
    inv = tt["inventory_type"]
    ttype = tt["type_name"]
    if inv == "WEAPONOFFHAND" and ttype == "Shield":
        inv = "SHIELD"
    if inv == "RANGED" and ttype in ("Gun", "Crossbow", "Wand"):
        inv = "RANGEDRIGHT"
    sub = subclass_id(cls, d.get("item_subclass"), inv)
    notes = []
    if tt["required_level"] is not None and d.get("required_level") not in (None, tt["required_level"]):
        notes.append(f"required level node {d.get('required_level')} vs tooltip {tt['required_level']}")
    if tt["item_level"] is not None and d.get("item_level") not in (None, tt["item_level"]):
        notes.append(f"item level node {d.get('item_level')} vs tooltip {tt['item_level']}")
    return {
        "name": d.get("name") or tt["name"], "quality": QUALITY.get(d.get("quality")),
        "item_level": d.get("item_level") if d.get("item_level") is not None else tt["item_level"],
        "required_level": d.get("required_level") if d.get("required_level") is not None else tt["required_level"],
        "inventory_type": inv, "class": cls, "subclass": sub,
        "subclass_name": d.get("item_subclass"), "type_name": ttype,
        "stats": tt["stats"], "weapon": tt["weapon"], "binding": tt["binding"], "unique": tt["unique"],
        "classes": tt["classes"] or None, "races": tt["races"] or None,
        "reputation": tt["reputation"], "skill": tt["skill"], "set": tt["set"],
        "effects": tt["effects"], "unparsed_effects": tt["unparsed_effects"],
        "unknown_lines": tt["unknown_lines"], "notes": notes, "sources": sources,
    }


def main() -> None:
    out, skipped = {}, 0
    for path in sorted((DIR / "tooltip").glob("*.json"), key=lambda p: int(p.stem)):
        item_id = int(path.stem)
        tooltip = json.loads(path.read_text(encoding="utf-8"))
        node_path = DIR / "node" / f"{item_id}.json"
        if "html" not in tooltip or not node_path.exists():
            skipped += 1
            continue
        out[item_id] = normalize(json.loads(node_path.read_text(encoding="utf-8")), tooltip, load_tabs(item_id))
    write_json(STAGING / "warcraftdb.json", out, compact=True)
    unparsed = sum(1 for i in out.values() if i["unparsed_effects"])
    unknown = sum(1 for i in out.values() if i["unknown_lines"])
    print(f"{len(out)} items ({skipped} unusable); {unparsed} with unparsed effects, {unknown} with unknown lines")


if __name__ == "__main__":
    main()
