"""Drop chances and vendor costs from the external collection (~/wowgear-external/wanted, or $WOWGEAR_EXTERNAL):
drop_chances.json -> data/forever/staging/external_drops.json: {item id: {npc id: {source: chance %}}};
vendor_requirements.json -> external_vendors.json: {item id: {vendor id: {"name", "found_in", "copper", "tokens"}}};
pvp_rank_rewards.json -> external_pvp.json: {item id: price in copper};
recipe_sources.json -> external_recipes.json: {crafted item id: how the recipe is learned (recipe_info)};
item_sets.json -> external_sets.json: game-client item sets (client_sets);
external_npc_names.json: {npc id: {"name", "zone"}} for the NPCs in external_drops (merge matches drops by name and
adds drops for items no other source places);
quest_rewards.json -> external_quests.json: {item id: [{"id", "name"}]} quests that give the item (quest_items),
  and external_quest_levels.json: {quest id: {"level", "min_level"}} for quests QuestieDB lacks (Forever-only ones).

Kept: NPC drops with a chance above 0 from Forever sources. Dropped: rows labelled Classic or built from Classic
emulator tables, sources we already read ourselves (warcraftdb, ForeverDB), and player samples under MIN_SAMPLE
kills. merge.py prefers published chances (PUBLISHED) and falls back to player samples (OBSERVED).

    python scripts/data/parse_external.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import ijson

sys.path.insert(0, os.path.dirname(__file__))
from _common import STAGING, read_json, write_json  # noqa: E402

EXTERNAL = Path(os.environ.get("WOWGEAR_EXTERNAL", Path.home() / "wowgear-external"))
PUBLISHED = {"icyveins": "Icy Veins", "stillsixty": "stillsixty", "NorgannonDB (GPL-3.0)": "NorgannonDB",
             "wowforever.gg item source": "wowforever.gg", "ForeverQuestLog": "ForeverQuestLog",
             "forever-xp.com dungeon and raid loot": "forever-xp"}
OBSERVED = {"Polestar Codex (player-recorded loot windows)": "Polestar Codex", "foreverdroprate": "foreverdroprate",
            "EG Link (Efficient Games, CC BY 4.0)": "EG Link", "Drop Tables (CC BY-SA 4.0)": "Drop Tables",
            "foreverdb.app NPC drop table": "foreverdb.app", "foreverdb.app item drop table": "foreverdb.app",
            "thewowdb player-recorded drop table": "TheWoWDB", "Zephras item Dropped by table": "Zephras",
            "Zephras NPC Drops table": "Zephras"}
MIN_SAMPLE = 20  # kills; fewer is noise
# Vendor rows (not NorgannonDB: it lists guards and quest NPCs as vendors): Icy Veins lists the base price, warcraftdb-forever sometimes the reputation-discounted one.
VENDOR_SOURCES = {"icyveins": "Icy Veins", "warcraftdb-forever": "warcraftdb", "warcraftdb-forever (item sold-by)": "warcraftdb",
                  "stillsixty": "stillsixty",
                  "EG Link (Efficient Games, CC BY 4.0)": "EG Link"}
VENDOR_ORDER = list(VENDOR_SOURCES)
# Easiest first: when several recipes make the same item, the first kind here wins.
RECIPE_KINDS = ["trainer", "automatic", "vendor", "quest", "rep", "favor", "drop", "unknown"]


def recipe_info(r: dict) -> dict:
    """{"kind", "name" (the recipe item), "vendors", "favor" (Merchant's Favor cost), "standing", "rep", "quests",
    "drops"}: how the recipe for a crafted item is learned."""
    kind, vendors = r.get("learned_from_kind"), r.get("vendors") or []
    psrc = [x for x in r.get("pattern_sources") or [] if isinstance(x, dict) and x.get("n")]
    quests = list(dict.fromkeys(f'{q["quest"]} (level {q["level"]})' if q.get("level") else q["quest"]
                                for q in r.get("eternadex_quests") or [] if q.get("quest_id")))
    rep = (r.get("reputation_source") or [None])[0] or next(
        (x["faction_standing"] for x in r.get("eternadex_reputation") or [] if x.get("faction_standing")), None)
    drops = re.sub(r"NPC \d+(, )?", "", r.get("drop_sources") or "").strip(", ") or ", ".join(  # unnamed NPC ids
        f'{x["n"]}{f" ({x['z']})" if x.get("z") else ""}' for x in psrc if x.get("t") in ("drop", "object"))[:200]
    if not vendors:
        vendors = [{"vendor": x["n"]} for x in psrc if x.get("t") == "vendor"]
    if kind == "item":
        kind = ("favor" if r.get("favor") else "rep" if rep else "vendor" if vendors else "quest" if quests
                else "drop" if drops else "unknown")
    elif kind not in ("trainer", "automatic"):
        kind = "unknown"
    names = [v["recipe_item"] for v in vendors if isinstance(v.get("recipe_item"), str)]
    out = {"kind": kind, "name": r.get("pattern_item_name") or next((n for n in names if not n.startswith("Recipe: ")),
                                                                    names[0] if names else None),
           "vendors": list(dict.fromkeys(v["vendor"] for v in vendors if v.get("vendor"))),
           "favor": r.get("favor"), "standing": r.get("favor_standing") if r.get("favor_standing") != "-" else None,
           "rep": rep, "quests": quests, "drops": drops or None}
    return {k: v for k, v in out.items() if v and (k in ("kind", "name") or k in KIND_FIELDS[kind])}


# Detail kept per kind, so the text shows how the chosen way works.
KIND_FIELDS = {"trainer": (), "automatic": (), "vendor": ("vendors",), "quest": ("quests",), "rep": ("rep", "vendors"),
               "favor": ("vendors", "favor", "standing"), "drop": ("drops",), "unknown": ()}


def sample(r: dict) -> int:
    """Kills behind an observed chance: sample/kills may be 15, "15", "6 / 30" or "1 of 1" (the larger number is the kills)."""
    nums = [int(n) for n in re.findall(r"\d+", f'{r.get("sample") or ""} {r.get("kills") or ""}')]
    return max(nums, default=0)


def quest_items(q: dict) -> set[str]:
    """Item ids a quest gives on the live server. Only EG Link's rows come from it: the other reward lists also
    carry unreleased content (AQ, ZG quests) and the rest of a chain's rewards (The Videre Elixir lists 16 items)."""
    eg = q.get("eglink") or {}
    return {str(x["id"]) for x in (eg.get("reward_items") or []) + (eg.get("choice_items") or [])}


def keep(r: dict) -> str | None:
    """Our label for a usable row, else None."""
    label = PUBLISHED.get(r.get("source")) or OBSERVED.get(r.get("source"))
    if not label or not r.get("npc_id") or not r.get("chance_pct") or "classic" in str(r.get("chance_provenance")).lower():
        return None
    if r["source"] in OBSERVED and (sample(r) < MIN_SAMPLE or r.get("trusted") is False):
        return None
    return label


def vendor_costs(rows: list[dict]) -> dict[str, dict]:
    """Per vendor id: name, the sites listing it, price in copper (first source in VENDOR_SOURCES that has it) and
    token costs (the longest list)."""
    out: dict[str, dict] = {}
    for r in sorted(rows, key=lambda r: VENDOR_ORDER.index(r["source"]) if r.get("source") in VENDOR_SOURCES else 99):
        if r.get("source") not in VENDOR_SOURCES or not r.get("vendor_id"):
            continue
        v = out.setdefault(str(r["vendor_id"]), {"found_in": []})
        if VENDOR_SOURCES[r["source"]] not in v["found_in"]:
            v["found_in"].append(VENDOR_SOURCES[r["source"]])
        if r.get("vendor") and "name" not in v:
            v["name"] = r["vendor"]
        if r.get("price") and "copper" not in v:
            v["copper"] = int(r["price"])
        tokens = [[t["name"], t["quantity"]] for t in r.get("tokens") or [] if t.get("name") and t.get("quantity")]
        if len(tokens) > len(v.get("tokens", [])):  # some sources leave out the Honor Points
            v["tokens"] = tokens
    for v in out.values():
        if "tokens" in v:  # ponytail: token vendors' "price" is the token count or the sell price; assumes no gold cost too
            v.pop("copper", None)
    return out


def stream(name: str, key: str):
    """(id, value) pairs under top-level `key` of a wanted/ file, one at a time: the files are up to 1.3 GB and
    json.load of them needs several times that in RAM."""
    with open(EXTERNAL / "wanted" / name, "rb") as f:
        yield from ijson.kvitems(f, key, use_float=True)


def client_sets() -> dict[str, dict]:
    """item_sets.json (game client ItemSet, via wago.tools) -> {set id: {name, pieces, bonuses: [{count, text}]}}.
    The client's own bonus text has $-placeholders for durations and procs; a site's rendered line for the same
    count replaces it when there is one."""
    out = {}
    for sid, s in read_json(EXTERNAL / "wanted" / "item_sets.json")["sets"].items():
        if s.get("source") != "wago.tools wowf DB2" or not s.get("pieces"):
            continue
        by_count: dict[int, str] = {}
        for b in s.get("bonuses") or []:
            text = re.sub(r"\$\{(\d+(?:\.\d+)?)\}\.\d", r"\1", (b.get("text") or "").strip())  # "${2}.1%": 2 shown with one decimal
            if text and b.get("count") and (b["count"] not in by_count or ("$" in by_count[b["count"]] and "$" not in text)):
                by_count[b["count"]] = text
        out[sid] = {"name": s["name"], "pieces": sorted(int(p["id"]) for p in s["pieces"]),
                    "bonuses": [{"count": c, "text": t} for c, t in sorted(by_count.items())]}
    return out


def main() -> None:
    sets = client_sets()
    write_json(STAGING / "external_sets.json", sets, compact=True)
    print(f"{len(sets)} item sets from the game client")
    vout = {iid: c for iid, rows in stream("vendor_requirements.json", "item_vendors") if (c := vendor_costs(rows))}
    token_vendors = {vid for c in vout.values() for vid, v in c.items() if "tokens" in v}
    for c in vout.values():  # their other "prices" are usually a token count with the token missing
        for vid in token_vendors & c.keys():
            c[vid].pop("copper", None)
    write_json(STAGING / "external_vendors.json", vout, compact=True)
    print(f"{len(vout)} items with vendors")
    ranks = read_json(EXTERNAL / "wanted" / "pvp_rank_rewards.json")["ranks"]
    pvp = {str(x["item_id"]): x["price"] for r in ranks.values() for x in r["items"] if x.get("price")}
    write_json(STAGING / "external_pvp.json", pvp, compact=True)
    print(f"{len(pvp)} PvP rank rewards with a price")
    recipes: dict[str, dict] = {}
    for _, r in stream("recipe_sources.json", "recipes"):
        info, old = recipe_info(r), recipes.get(str(r.get("item")))
        if r.get("item") and (not old or RECIPE_KINDS.index(info["kind"]) < RECIPE_KINDS.index(old["kind"])):
            recipes[str(r["item"])] = info
    write_json(STAGING / "external_recipes.json", recipes, compact=True)
    print(f"{len(recipes)} crafted items with recipe info")
    quests: dict[str, list] = {}
    levels: dict[str, dict] = {}
    for qid, q in stream("quest_rewards.json", "quests"):
        for iid in quest_items(q):
            quests.setdefault(iid, []).append({"id": int(qid), "name": q.get("name")})
        lv = {k: int(q[k]) for k in ("level", "min_level") if str(q.get(k) or "").isdigit() and int(q[k]) > 0}
        if lv:
            levels[qid] = lv
    write_json(STAGING / "external_quests.json", quests, compact=True)
    write_json(STAGING / "external_quest_levels.json", levels, compact=True)
    print(f"{len(quests)} items given by quests")
    out: dict[str, dict] = {}
    names: dict[str, dict] = {}
    for iid, rows in stream("drop_chances.json", "items"):
        for r in rows:
            label = keep(r)
            if label:
                n = names.setdefault(str(r["npc_id"]), {"name": None, "zone": None})
                n["name"], n["zone"] = n["name"] or r.get("npc"), n["zone"] or r.get("zone") or r.get("instance")
                by = out.setdefault(iid, {}).setdefault(str(r["npc_id"]), {})
                by.setdefault(label, round(float(r["chance_pct"]), 4))  # first row per source wins (item page)
    write_json(STAGING / "external_drops.json", out, compact=True)
    write_json(STAGING / "external_npc_names.json", names, compact=True)
    print(f"{len(out)} items, {sum(len(v) for v in out.values())} item/NPC pairs with a chance")


assert quest_items({"guaranteed": [{"item_id": 1}], "eglink": {"reward_items": [{"id": 2}], "choice_items": None}}) == {"2"}
assert sample({"sample": "6 / 30"}) == 30 and sample({"sample": 15}) == 15 and sample({"kills": 25}) == 25 and sample({}) == 0

if __name__ == "__main__":
    main()

