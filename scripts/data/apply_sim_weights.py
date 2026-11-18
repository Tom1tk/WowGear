"""Turn MythicSim's simmed EP (data/forever/mythicsim_ep.json) into our weights (data/forever/weights.json).

Our weights are equivalence points in each profile's base unit (AP, ranged AP or spell power), per point for
primary stats and per 1% for rating stats. MythicSim gives EP per point (per rating point for hit/crit/haste/
expertise), so: ours = EP / EP(base) * ratings-per-1%. Forever unifies melee and spell hit/crit, so an item's hit
counts as Hit + Spell hit (same for crit). Tank and healer profiles are left alone: MythicSim sims damage/threat
only and has no healer pages. Run after copying new numbers into mythicsim_ep.json, then build_gear.py.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data" / "forever"
RATING_PER_PCT = {"hit": 10, "crit": 14, "haste": 10, "expertise": 10}  # same as backend/app/scoring.py
NAMES = {"Strength": "str", "Agility": "agi", "Intellect": "int", "Spirit": "spi", "Attack power": "ap",
         "Ranged attack power": "rap", "Spell damage": "sp", "Mana per 5": "mp5", "Feral attack power": "feral_ap",
         "Hit": "hit", "Spell hit": "hit", "Crit": "crit", "Spell crit": "crit", "Haste": "haste",
         "Spell haste": "haste", "Expertise": "expertise"}
MANA_KEYS = ("spi", "mp5")  # downtime matters while levelling; keep the hand-set levelling values


def base_name(spec: str, ep: dict) -> str:
    if spec.startswith("hunter."):
        return "Ranged attack power"
    return "Attack power" if "Attack power" in ep else "Spell damage"


def convert(spec: str, ep: dict) -> dict:
    base = ep[base_name(spec, ep)]
    out: dict[str, float] = {}
    for name, value in ep.items():
        key = NAMES.get(name) or (f"sp_{name.split()[0].lower()}" if name.endswith(" spell damage") else None)
        if key:
            out[key] = out.get(key, 0) + value / base * RATING_PER_PCT.get(key, 1)
    return {k: max(0.0, round(v, 2)) for k, v in out.items()}  # a negative EP is sim noise (e.g. Fire haste)


def main() -> None:
    sim = json.loads((DATA / "mythicsim_ep.json").read_text())["specs"]
    path = DATA / "weights.json"
    weights = json.loads(path.read_text())
    for spec, entry in sim.items():
        prof = weights["profiles"][spec]
        old_end, old_lvl = prof["endgame"], prof["leveling"]
        new = convert(spec, entry["ep"])
        if new.get("hit", 0) <= 0 and old_end.get("hit"):  # reference build sits at the hit cap: sim reads 0
            new["hit"] = old_end["hit"]
        end = {**old_end, **new}
        lvl = {}
        for k, v in end.items():
            if k in old_lvl and (k in MANA_KEYS or k not in new):
                lvl[k] = old_lvl[k]  # hand-set levelling value (mana, Stamina, armor ...)
            elif old_end.get(k) and k in old_lvl:
                lvl[k] = round(v * old_lvl[k] / old_end[k], 2)  # keep the old levelling/endgame ratio
            else:
                lvl[k] = v
        prof["endgame"], prof["leveling"] = end, lvl
        note = f"https://mythicsim.com/wow-forever/stat-priority/{entry['page']} (simmed EP, {entry['build']}, 2026-11-18)"
        prof["sources"] = [s for s in prof.get("sources", []) if "mythicsim.com" not in s] + [note]
    path.write_text(json.dumps(weights, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
