"""QuestieDB Forever data (quests, NPC zones) -> data/forever/staging/questie.json.

Reads data/raw/git/QuestieDB/data/Forever/foreverQuestDB.lua and foreverNpcDB.lua (GPL-3, see
the repo's LICENSE). Output:
  quests: {id: {"name", "level", "zone" (area id or null), "chain" (see build_chains, only when in a chain)}}
  npcs:   {id: area id}

    python scripts/data/parse_questie.py
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import RAW, STAGING, lua_value, write_json  # noqa: E402

DB = RAW / "git" / "QuestieDB" / "data" / "Forever"
Q_NAME, Q_LEVEL, Q_REQ, Q_PRE_GROUP, Q_PRE_SINGLE, Q_ZONE, Q_NEXT = 1, 5, 4, 12, 13, 17, 22
N_ZONE = 9
def read_rows(path) -> dict[int, list]:
    """{id: [fields...]} from a Questie data file (lines like `[12] = {...},`)."""
    out = {}
    for line in path.read_text(encoding="utf-8").split("\n"):
        m = re.match(r"^\[(\d+)\] = (\{.*\}),?\s*$", line)
        if m:
            out[int(m.group(1))] = lua_value(m.group(2))[0]
    return out


def field(row: list, idx: int):
    return row[idx - 1] if len(row) >= idx else None


def build_chains(quests: dict[int, dict]) -> dict[int, dict]:
    """quests: {id: {"name", "level", "pre": [ids], "next": id|None}} ->
    {id: {"pos", "len", "first_id", "first_name", "first_level"}} for quests in a chain of 2+.
    pos = 1 + steps back to the chain start (first listed prerequisite each time); len = pos + the longest
    way forward (quests whose prerequisites or nextQuestInChain point here)."""
    kids: dict[int, set] = {}
    for qid, q in quests.items():
        for p in q.get("pre") or []:
            kids.setdefault(p, set()).add(qid)
        if q.get("next") in quests:
            kids.setdefault(qid, set()).add(q["next"])
    parent = {}
    for qid, q in quests.items():
        pre = [p for p in q.get("pre") or [] if p in quests and p != qid]
        if pre:
            parent[qid] = pre[0]
    forward: dict[int, int] = {}

    def depth(q, seen=()):
        if q in forward:
            return forward[q]
        best = 0
        for k in kids.get(q, ()):
            if k not in seen and k != q:
                best = max(best, 1 + depth(k, seen + (q,)))
        forward[q] = best
        return best

    out = {}
    for qid in quests:
        first, steps, seen = qid, 0, {qid}
        while first in parent and parent[first] not in seen:
            first = parent[first]
            seen.add(first)
            steps += 1
        length = steps + 1 + depth(qid)
        if length >= 2:
            f = quests[first]
            out[qid] = {"pos": steps + 1, "len": length, "first_id": first, "first_name": f.get("name"),
                        "first_level": f.get("level")}
    return out


def main() -> None:
    quests = {}
    for qid, row in read_rows(DB / "foreverQuestDB.lua").items():
        pre = (field(row, Q_PRE_SINGLE) or []) or (field(row, Q_PRE_GROUP) or [])
        quests[qid] = {"name": field(row, Q_NAME), "level": field(row, Q_LEVEL) or field(row, Q_REQ),
                       "zone": field(row, Q_ZONE), "pre": pre, "next": field(row, Q_NEXT)}
    chains = build_chains(quests)
    out_q = {}
    for qid, q in quests.items():
        rec = {"name": q["name"], "level": q["level"], "zone": q["zone"] if (q["zone"] or 0) > 0 else None}
        if qid in chains:
            rec["chain"] = chains[qid]
        out_q[qid] = rec
    npcs = {nid: field(row, N_ZONE) for nid, row in read_rows(DB / "foreverNpcDB.lua").items()}
    write_json(STAGING / "questie.json", {"quests": out_q, "npcs": {k: v for k, v in npcs.items() if v}}, compact=True)
    print(f"{len(out_q)} quests ({len(chains)} in a chain), {len(npcs)} npcs")


if __name__ == "__main__":
    main()
