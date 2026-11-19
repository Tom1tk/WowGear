"""Drop chances and vendor costs from the external collection (~/wowgear-external/wanted, or $WOWGEAR_EXTERNAL):
drop_chances.json -> data/forever/staging/external_drops.json: {item id: {npc id: {source: chance %}}};
vendor_requirements.json -> external_vendors.json: {item id: {vendor id: {"name", "found_in", "copper", "tokens"}}};
pvp_rank_rewards.json -> external_pvp.json: {item id: price in copper}.

Kept: NPC drops with a chance above 0 from Forever sources. Dropped: rows labelled Classic or built from Classic
emulator tables, sources we already read ourselves (warcraftdb, ForeverDB), and player samples under MIN_SAMPLE
kills. merge.py prefers published chances (PUBLISHED) and falls back to player samples (OBSERVED).

    python scripts/data/parse_external.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from _common import STAGING, read_json, write_json  # noqa: E402

EXTERNAL = Path(os.environ.get("WOWGEAR_EXTERNAL", Path.home() / "wowgear-external"))
PUBLISHED = {"icyveins": "Icy Veins", "stillsixty": "stillsixty", "NorgannonDB (GPL-3.0)": "NorgannonDB",
             "wowforever.gg item source": "wowforever.gg"}
OBSERVED = {"Polestar Codex (player-recorded loot windows)": "Polestar Codex", "foreverdroprate": "foreverdroprate",
            "EG Link (Efficient Games, CC BY 4.0)": "EG Link", "Drop Tables (CC BY-SA 4.0)": "Drop Tables"}
MIN_SAMPLE = 20  # kills; fewer is noise
# Vendor rows (not NorgannonDB: it lists guards and quest NPCs as vendors): Icy Veins lists the base price, warcraftdb-forever sometimes the reputation-discounted one.
VENDOR_SOURCES = {"icyveins": "Icy Veins", "warcraftdb-forever": "warcraftdb", "warcraftdb-forever (item sold-by)": "warcraftdb",
                  "stillsixty": "stillsixty",
                  "EG Link (Efficient Games, CC BY 4.0)": "EG Link"}
VENDOR_ORDER = list(VENDOR_SOURCES)


def keep(r: dict) -> str | None:
    """Our label for a usable row, else None."""
    label = PUBLISHED.get(r.get("source")) or OBSERVED.get(r.get("source"))
    if not label or not r.get("npc_id") or not r.get("chance_pct") or "classic" in str(r.get("chance_provenance")).lower():
        return None
    if r["source"] in OBSERVED and ((r.get("sample") or r.get("kills") or 0) < MIN_SAMPLE or r.get("trusted") is False):
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


def main() -> None:
    vendors = read_json(EXTERNAL / "wanted" / "vendor_requirements.json")["item_vendors"]
    vout = {iid: c for iid, rows in vendors.items() if (c := vendor_costs(rows))}
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
    out: dict[str, dict] = {}
    for iid, rows in read_json(EXTERNAL / "wanted" / "drop_chances.json")["items"].items():
        for r in rows:
            label = keep(r)
            if label:
                by = out.setdefault(iid, {}).setdefault(str(r["npc_id"]), {})
                by.setdefault(label, round(float(r["chance_pct"]), 4))  # first row per source wins (item page)
    write_json(STAGING / "external_drops.json", out, compact=True)
    print(f"{len(out)} items, {sum(len(v) for v in out.values())} item/NPC pairs with a chance")


if __name__ == "__main__":
    main()
