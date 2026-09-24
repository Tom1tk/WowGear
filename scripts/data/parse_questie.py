"""Parse QuestieDB Classic Era data (items, NPCs, quests, objects) + Era fixes.

QuestieDB (https://github.com/Questie/QuestieDB) is the database of the
Questie addon, maintained for Classic Era. It gives item sources (NPC drops,
object drops, quest rewards, vendors) and quest / NPC details. Stats are not
in it. The raw Lua tables are evaluated with lupa; the Era correction files
are applied on top, the same way the addon does at runtime.

    git clone --depth 1 https://github.com/Questie/QuestieDB data/raw/git/QuestieDB
    python scripts/data/parse_questie.py
"""

from __future__ import annotations

import os
import sys

import lupa

sys.path.insert(0, os.path.dirname(__file__))
from _common import RAW, STAGING, write_json  # noqa: E402

QDB = RAW / "git" / "QuestieDB"

STUB = r"""
local function auto()
  -- Unknown constants resolve to 0 so correction files load without the addon.
  return setmetatable({}, {__index = function(t, k)
    local v = auto(); rawset(t, k, v); return v end,
    __call = function(_, a) return a end,
    __unm = function() return 0 end, __add = function() return 0 end,
    __sub = function() return 0 end, __mul = function() return 0 end,
    __bor = function() return 0 end, __band = function() return 0 end,
    __concat = function() return "" end})
end
local modules = {}
QuestieLoader = {}
function QuestieLoader:CreateModule(name) modules[name] = modules[name] or auto(); return modules[name] end
function QuestieLoader:ImportModule(name) modules[name] = modules[name] or auto(); return modules[name] end
UnitFactionGroup = function() return "Alliance" end
Questie = auto()
C_Timer = auto()
function __modules() return modules end
"""


def lua_to_py(value):
    if lupa.lua_type(value) == "table":
        keys = list(value.keys())
        if keys and all(isinstance(k, int) for k in keys) and sorted(keys) == list(range(1, len(keys) + 1)):
            return [lua_to_py(value[k]) for k in keys]
        return {k: lua_to_py(v) for k, v in value.items()}
    return value


def load_kind(lua, kind: str, fname: str):
    """Evaluate data/Classic/classic<Kind>DB.lua; returns (keys, data table)."""
    lua.execute((QDB / "data" / "Classic" / fname).read_text(encoding="utf-8"))
    qdb = lua.eval("__modules()['QuestieDB']")
    keys = {k: int(v) for k, v in qdb[f"{kind}Keys"].items()}
    data = lua.execute(qdb[f"{kind}Data"])
    return keys, data


def enum_constants(lua):
    """Load src/corrections/enum/*.lua into a constants table."""
    lua.execute("__enum = {}")
    for path in sorted((QDB / "src" / "corrections" / "enum").glob("*.lua")):
        if path.name == "constants.lua":
            continue
        chunk = lua.eval(f"function(src) return load(src, '{path.name}') end")(path.read_text(encoding="utf-8"))
        chunk("QuestieDB", lua.eval("{Enum = __enum}"))
    return lua.eval("__enum")


def apply_fixes(lua, data, fix_file: str, module: str, loader: str = "Load"):
    lua.execute((QDB / "src" / "corrections" / "Era" / fix_file).read_text(encoding="utf-8"))
    fixes = lua.eval(f"__modules()['{module}']:{loader}()")
    count = 0
    for entity_id, changes in fixes.items():
        row = data[entity_id]
        if row is None:
            row = lua.table()
            data[entity_id] = row
        for key, value in changes.items():
            row[key] = value
        count += 1
    return count


def rows(keys, data):
    out = {}
    for entity_id, row in data.items():
        rec = {}
        for name, idx in keys.items():
            val = row[idx]
            if val is None:
                continue
            if name in ("spawns", "waypoints") and lupa.lua_type(val) == "table":
                rec[name] = sorted(int(z) for z in val.keys())  # zone ids only
            else:
                rec[name] = lua_to_py(val)
        out[int(entity_id)] = rec
    return out


def main() -> None:
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(STUB)
    enum = enum_constants(lua)
    qdb = lua.eval("QuestieLoader:ImportModule('QuestieDB')")
    for name in ("itemClasses", "questFlags", "specialFlags", "raceKeys", "classKeys", "npcFlags"):
        if enum[name] is not None:
            qdb[name] = enum[name]
    era = enum["byExpansion"][1] or enum["byExpansion"]["Era"] or enum["byExpansion"]["Classic"]
    for name in ("raceKeys", "classKeys", "npcFlags"):
        if era is not None and era[name] is not None:
            qdb[name] = era[name]
    zone = lua.eval("QuestieLoader:ImportModule('ZoneDB')")
    zone["zoneIDs"] = enum["zoneIDs"]
    qdb["factionIDs"] = enum["factionIDs"]
    qdb["sortKeys"] = enum["sortKeys"]

    result = {}
    for kind, fname, fix, module in (
        ("item", "classicItemDB.lua", "classicItemFixes.lua", "QuestieItemFixes"),
        ("npc", "classicNpcDB.lua", "classicNPCFixes.lua", "QuestieNPCFixes"),
        ("object", "classicObjectDB.lua", "classicObjectFixes.lua", "QuestieObjectFixes"),
        ("quest", "classicQuestDB.lua", "classicQuestFixes.lua", "QuestieQuestFixes"),
    ):
        keys, data = load_kind(lua, kind, fname)
        qdb[f"{kind}Keys"] = lua.table_from(keys)
        try:
            n = apply_fixes(lua, data, fix, module)
        except lupa.LuaError as exc:  # keep raw data if a fix file needs more stubs
            print(f"WARN {fix}: {exc}")
            n = 0
        parsed = rows(keys, data)
        if kind == "npc":  # coordinates are not needed; keep zone ids only
            for rec in parsed.values():
                if isinstance(rec.get("spawns"), dict):
                    rec["spawns"] = sorted(int(z) for z in rec["spawns"])
                rec.pop("waypoints", None)
        if kind == "object":
            for rec in parsed.values():
                if isinstance(rec.get("spawns"), dict):
                    rec["spawns"] = sorted(int(z) for z in rec["spawns"])
                rec.pop("waypoints", None)
        if kind == "quest":
            for rec in parsed.values():
                for drop in ("objectivesText", "triggerEnd", "extraObjectives", "objectives"):
                    rec.pop(drop, None)
        result[kind] = parsed
        print(f"{kind}: {len(parsed)} rows, {n} Era fixes applied")

    zone_ids = {int(v): k for k, v in lua_to_py(enum["zoneIDs"]).items()}
    write_json(STAGING / "questie.json", {"zones": zone_ids, **result}, compact=True)


if __name__ == "__main__":
    main()
