# WowGear Classic

The best gear for **every level from 10 to 60** in **WoW Classic Era**, for every
class and spec, and where to get each item.

- **Look up a character** (Blizzard API, Era realms): the site reads your level,
  race, class, talents (to find your spec) and equipped gear, and compares.
- **Enter manually**: pick race, class, spec and level, then tick the items you have
  (saved in your browser).
- A **level slider** shows the best items at any level. At 60 you can pick the content
  tier: pre-raid, Molten Core/Onyxia, Blackwing Lair/Zul'Gurub, Ahn'Qiraj, Naxxramas.
- **What to do next** groups the upgrades by where to go (dungeon, quest, vendor,
  crafting, Auction House), biggest gain first. **Coming up** lists the next levels
  where a better item becomes available.

## How the gear lists are made

The lists are **calculated**, not copied from one guide:

1. `scripts/data/` collects item and source data from several sources and merges it.
   Each fact keeps its sources; a fact is *confirmed* when two sources agree.
2. Every usable item gets a score from the spec's stat weights (`data/era/weights.json`).
3. For each level (and raid tier at 60) the highest-scoring items the character can
   equip and get by that level are kept. Easy sources (quests, vendors, likely drops)
   rank slightly above hard ones (random world drops).
4. The results are checked against human-made lists (`reports/validation.md`).

| Source | Used for |
|---|---|
| Blizzard Game Data API (Classic Era, `classic1x` namespaces) | item stats, rules, level requirements (reference) |
| [QuestieDB](https://github.com/Questie/QuestieDB) (Era data + Era fixes) | drops, quest rewards, vendors, NPCs, quests |
| [CMaNGOS classic-db](https://github.com/cmangos/classic-db), VMaNGOS world DB (patch 1.12) | cross-check of stats, loot tables, quests |
| [AtlasLootClassic](https://github.com/Hoizame/AtlasLootClassic) | boss loot, crafted items + reagents, instance level ranges |
| wowtbc.gg pre-raid lists, NoobToBoss leveling guide | validation only |

Not used: Wowhead and wago.tools data (their robots.txt does not allow automated
access). Wowhead is only used for item links and tooltips on the page.

Known limits:
- Random-suffix items ("… of the Monkey") have no fixed stats and are left out.
- PvP rank and battleground reputation rewards are left out (PvE lists).
- Special effects (procs, "Use:") count only when listed in `data/era/effects.json`;
  other items show a "special effect" badge.
- Lists are per faction, not per race, so racial weapon skills only count where the
  class has one race in that faction.

## Run locally

```bash
python3 -m venv .venv   # Python 3.11+ && .venv/bin/pip install -r requirements.txt pytest
cp .env.example .env   # add BLIZZARD_CLIENT_ID / BLIZZARD_CLIENT_SECRET (develop.battle.net)
.venv/bin/uvicorn backend.app.main:app --reload
```

Open http://127.0.0.1:8000. Without a key, manual mode still works.

## API

- `GET /api/health`
- `GET /api/realms?region=eu` — Classic Era realms
- `GET /api/character?region=&realm=&name=` — profile, equipped items (with scores),
  talent points and the detected spec
- `POST /api/score` — `{class_id, spec, level, race_id?, item_ids}` → item scores

The gear lists are static files: `frontend/data/gear/<class>.<spec>.<A|H>.json` and
`frontend/data/meta.json`.

## Rebuild the data

```bash
.venv/bin/pip install -r requirements-data.txt
# raw inputs go to data/raw/ (git-ignored)
git clone --depth 1 https://github.com/Questie/QuestieDB data/raw/git/QuestieDB
git clone --depth 1 https://github.com/Hoizame/AtlasLootClassic data/raw/git/AtlasLootClassic
# CMaNGOS: gunzip cmangos/classic-db Full_DB/*.sql.gz -> data/raw/cmangos/classicdb.sql
# VMaNGOS: extract brotalnia/database world_full_*.7z -> data/raw/vmangos/world.sql
.venv/bin/python scripts/data/fetch_blizzard_items.py   # needs the API key in .env
.venv/bin/python scripts/data/parse_blizzard.py
.venv/bin/python scripts/data/parse_questie.py
.venv/bin/python scripts/data/parse_mangos.py
.venv/bin/python scripts/data/parse_atlasloot.py
.venv/bin/python scripts/data/merge.py        # -> data/era/items.json, sources.json, reports/
.venv/bin/python scripts/data/build_gear.py   # -> frontend/data/
.venv/bin/python scripts/data/fetch_reference.py && .venv/bin/python scripts/data/validate.py
```

To tune a spec, edit `data/era/weights.json` (or `effects.json` / `exclude.json`),
then run `build_gear.py` and `validate.py` again.

## Tests

`.venv/bin/pytest` (API, Blizzard parsing, class rules, scoring, gear data sanity).
Browser checks: `cd scripts && npm i && node verify.mjs http://localhost:8000 us/<realm> <character>`.

## Reports

- `reports/validation.md` — our lists vs human-made lists
- `reports/conflicts.md` — merge summary and stat differences between sources
- `reports/instances.md` — dungeon level ranges vs boss levels
