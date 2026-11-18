"""ForeverDB.net addon data (GearSources.lua) -> staging/foreverdb.json.

Data from ForeverDB.net (https://foreverdb.net), GPL-3.0; credit required (see its NOTICE.txt).
Fetch: the files listed in https://foreverdb.net/downloads/addon-manifest.json (robots allows them;
the /api/ is not used), cached in data/raw/foreverdb/. Row format: "id36|name|groups|flags|side|twin|limit|sources".
Source labels: s seen in Forever, c clue, f Forever client, k CLASSIC DATA (must not be used as truth).
Sources stay raw strings; flagged k entries are listed in `classic_labelled`.

    python scripts/data/parse_foreverdb.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import RAW, STAGING, lua_value, write_json  # noqa: E402


def parse_gear_sources(text: str) -> dict[int, dict]:
    out = {}
    for line in text.split("\n"):
        p = line.split("|")
        if len(p) < 8 or not p[0].isalnum():
            continue
        srcs = [s.split("^") for s in "|".join(p[7:]).split("~")]
        out[int(p[0], 36)] = {"name": p[1], "groups": p[2], "flags": p[3], "side": p[4] or None,
                              "sources": srcs, "classic_labelled": any(s[-1] == "k" for s in srcs)}
    return out


def parse_gear_sets(text: str) -> dict[int, dict]:
    """GearSets.lua -> {set id: {name, kind, level, pieces: [item ids]}} (ids equal Blizzard item_set ids)."""
    table, _ = lua_value(text, text.index("ns.gearSets=") + len("ns.gearSets="))
    return {s[0]: {"name": s[1], "kind": s[2], "level": s[5], "pieces": s[6][0::3]} for s in table["sets"]}


def main() -> None:
    items = parse_gear_sources((RAW / "foreverdb" / "GearSources.lua").read_text(encoding="utf-8"))
    write_json(STAGING / "foreverdb.json", items, compact=True)
    sets = parse_gear_sets((RAW / "foreverdb" / "GearSets.lua").read_text(encoding="utf-8"))
    write_json(STAGING / "foreverdb_sets.json", sets, compact=True)
    print(f"{len(sets)} sets, {len(items)} items, {sum(i['classic_labelled'] for i in items.values())} with Classic-labelled sources")


if __name__ == "__main__":
    main()
