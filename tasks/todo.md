# WowGear Classic — status

Plan: `tasks/classic-era-plan.md`. This file tracks what is done and what is next.

## M0 research report (2026-09-24)

| Source | Result |
|---|---|
| Blizzard API, Era (`classic1x`) | Works with the project key: item + item search (static), realm index (dynamic), character profile / equipment / specializations (talent points per tree) / media (profile). Journal, profession, recipe and spell endpoints return 404 for Era. |
| Blizzard Armory (Era pages) | Not needed: the Profile API works. `armory.py` removed. |
| QuestieDB (GitHub) | Era item sources (NPC/object/container drops, quest rewards, vendors), NPCs, quests, plus Era correction files. Cloned with git, read with `lupa`. |
| CMaNGOS classic-db, VMaNGOS world DB (GitHub) | Patch 1.12 emulator data (stats, loot tables with chances, quests, vendors). Cross-check only: Era changed some items. Non-commercial fair-use notice (CMaNGOS) — we store derived facts only. |
| AtlasLootClassic (GitHub, GPL-2.0) | Boss loot per instance, crafted items with reagents, level ranges. |
| Wowhead | robots.txt blocks AI agents by name → **not used for data**, only item links/tooltips on the page. |
| wago.tools | robots.txt disallows everything → not used. |
| Icy Veins | Cloudflare blocks automated access from this environment → not used. |
| wowtbc.gg, NoobToBoss | robots.txt allows → used as validation references only. |

## Done

- [x] M1 branch `classic-era`; Retail code removed (Icy Veins scraper, armory, retail recommend engine, retail UI).
- [x] M2 hand tables: `data/era/instances.json` (33/34 ranges confirmed by boss levels), `classes.json`.
- [x] M3 pipeline: fetch/parse/merge with provenance, conflict + instance reports.
- [x] M4 weights for all 9 classes (21 profiles), per-level builder, validation (70% agreement incl. close calls).
- [x] M5 manual mode + checklist, slider (every level 10–60, as the owner asked instead of 10-level brackets), raid tiers at 60.
- [x] M6 all classes and specs (50 gear files).
- [x] M7 level 60 tiers are computed (Icy Veins was not reachable); raid-gated quests and crafted items with raid materials go to the right tier.
- [x] M8 character lookup via the Era Profile API, spec detection from talents.
- [x] Report-a-wrong-item link (GitHub issue with context).

## Next / open

- [ ] Owner: create the `retail-final` tag on `main` (tag push is blocked in the build environment).
- [ ] Owner: rotate the Blizzard client secret (it was shared in a chat), then update `.env` / Vercel.
- [ ] Point Vercel production at `classic-era`, then make it the new `main` (M9).
- [ ] Tune weights where validation is weakest: Fire Mage (50%), Elemental (56%), Warlocks (59%).
- [ ] Random-suffix greens ("… of the Monkey") are left out; add a generic hint per slot.
- [ ] More `effects.json` entries (weapon procs, "Use:" trinkets).
- [ ] Per-race lists (racial weapon skills) if the file size allows.
- [ ] WoW Forever (launch 4 Nov 2026): QuestieDB already has a `forever` branch/data folder; review then.
