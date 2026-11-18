# Plan: rebuild WowGear for WoW Forever

Status: v1 — branch `forever` (from `main` @ 620a328, the Classic Era site).
Date: 2026-11-18. Owner of the plan: orchestrator. Implementation: sub-agents (W1–W5).

## 0. Decisions

| Topic | Decision |
|---|---|
| Branch | `forever`, from `main`. `main` stays the Classic Era site until the owner switches Vercel. |
| Game scope | WoW Forever only (launched 4 Nov 2026). Era code paths and `data/era/` are removed on this branch (Era lives on `main`/`classic-era`). |
| Levels | Slider 10–60 (the armory and API only show characters from level 10). |
| Level 60 tiers | 0 = Pre-raid (dungeons incl. the 9 new ones, quests, rep, crafted). 1 = Raid tier 1: The Barrow Deeps (10), Hyjal Summit (20), Onyxia's Lair (40) — open 9 Dec 2026. No MC/BWL/AQ/Naxx. Tier list is data-driven from `instances.json`, so spring/summer 2027 raids are a table edit. |
| Uncertainty | Every fact keeps its sources. **Sources disagree → "Uncertain" badge** on the page with the differing values. One source only → small "1 source" note. Two agree → normal. Raid loot before 9 Dec is datamined → whole tier flagged uncertain. |
| Wowhead | robots.txt disallows `anthropic-ai` / `ClaudeBot` → **not fetched**. Used only for item links + tooltips in the page (`wowhead.com/forever/item=ID`). |
| Characters | No realms. Lookup by **region + first name + surname** (`{name}-{surname}` slug, unique per region). Show the character's **ruleset** (Normal / PvP / RP / RP-PvP / later Hardcore). Rulesets do not change gear lists (PvE), so they are display only. |
| Commits | Sub-agents do not commit. Orchestrator audits, then commits as Tom1tk (no Claude trailers). |
| Test data | Fixtures use invented characters / ids only (public repo). |

## 1. What is different in Forever (facts the build must respect)

- Cap 60, permanent. 9 classes, 3 talent trees each (new 16-point milestone talents; detection by points per tree still works). Dual spec at 40.
- Races: 8 original + **Skyborne** (new, paid; starts Zephras Isle 1–12). Six new race/class combos → W2 must research the combo table + Skyborne faction.
- Items: original items exist but **many stats/sources changed** (dungeon loot reworked, quest rewards reworked in Duskwood/STV, Spell Power as a stat on some items, e.g. Soulforge Armor). Thousands of new items/quests (1,000+ quests, mostly 30–50).
- New zones: Zephras Isle (1–12), Riverglades (~35–45), Shen'dralas, expanded Mount Hyjal (60).
- New dungeons (third-party ranges, W2 must confirm with a 2nd source):
  Hall of Thanes 13–18 (A, under Ironforge), Ruins of Lordaeron 15–20 (H?, Tirisfal), Excavation Site: Wetlands 24–29, City of Dalaran 28–33, The Drowned City 35–40, Krol'dok Stronghold 40–45, Alcaz Prison 48–53, Blackmaw Hold 55–60, Shaper's Terrace 58–60. All original dungeons return with reworked loot. One difficulty.
- Class rework is large (e.g. Shaman Lightning Bolt/Stormstrike, cat Shred 200%, poisons scale 2× AP, warlock pets). Stat weights from Era are a starting point only and must be reviewed per spec (W3).
- PvP: honor gear + ranks — out of scope (PvE lists), same as Era.

## 2. Data sources and the cross-reference rule

| Source | Access | Gives | Used for |
|---|---|---|---|
| QuestieDB `data/Forever/` (foreverItemDB/NpcDB/ObjectDB/QuestDB.lua, conversion.json), GPL-3 | git clone (`data/raw/git/QuestieDB`) | item name/ilvl/req level/class/subclass, drops (npc/object/item), quest rewards, vendors, npc levels + zones, quest levels/faction | sources, levels, rules |
| forever.warcraftdb.com (robots: `Allow: /`) | `/api/v1/tooltip/item/{id}` (tooltip HTML: slot, type, stats, armor, weapon dmg/speed, binding, unique, effects, req level, class limit), `/api/data/node/item/{id}` (ilvl, req level, quality, class, source kind), `/api/data/node/item/{id}/tab/{slug}?page=N` (dropped-by with chance, reward-from, sold-by, created-by …); sitemap `/sitemap/item.xml` | stats + sources | second independent source; **only stats source without a Blizzard key** |
| Blizzard Game Data API `static-forever-{region}` | needs key in `.env` (optional) | item stats, req level, inventory type | third source when a key is present; ~40 % of ids 404 → missing is not a conflict |
| Other Forever databases (e.g. foreverdb.net) | only if robots.txt allows | — | W1 checks; add if allowed and cheap |
| Era data | — | — | **not** a source (Forever changed items) |

Fetching rules: obey robots.txt, identify with a generic UA (`WowGearBot/1.0 (+https://github.com/Tom1tk/WowGear)`), ≤ 2 requests/s, cache every raw response under `data/raw/` (git-ignored) and re-run from cache. Only fetch items that can be gear (equippable armor/weapons/rings/necks/trinkets/relics/off-hands, quality ≥ common, req level ≤ 60) — filter the 24.7k sitemap ids with QuestieDB class/subclass first; warcraftdb node data second.

**Cross-reference (merge.py)**, per item:
- Fields compared: name, required_level, item_level, inventory_type/slot, class+subclass, stats, weapon dmg/speed, binding, class restriction.
- `checks[field]` = `confirmed` (≥ 2 sources agree), `single` (1 source), `conflict` (disagree; keep all values `{source: value}`).
- Sources (where to get it): each source entry keeps `found_in: [...]`, `confirmed` (≥ 2 found it), `conflict` (e.g. drop chance differs > 2×, or quest/npc in one source only while the other lists a different one).
- Item-level `uncertain: [str]` = human-readable reasons for every conflict, e.g. `"Stats differ: warcraftdb +12 Strength, Blizzard +10 Strength"`, `"Required level: QuestieDB 42, warcraftdb 45"`. Empty list = fine.
- Value used for scoring on conflict: Blizzard > warcraftdb > QuestieDB (most direct client data first), but the item still shows Uncertain.
- `reports/conflicts.md`: counts per field and per source pair, top 50 examples.

## 3. Output contract (frontend ↔ pipeline). Keep Era shape; additions in **bold**.

`frontend/data/meta.json`
```json
{ "built": "YYYY-MM-DD", "game": "forever",
  "classes": {"<class_id>": {"name","slug","leveling_spec","specs":{"<key>":"Name"}}},
  "races": {"<race_id>": {"name","slug","faction":"A|H","classes":[ids]}},
  "instances": {"<key>": {"name","zone","levels":[lo,hi],"side":"A|H|null","tier":0|1,"type":"dungeon|raid10|raid20|raid40","note", **"uncertain": [str]**}},
  "tiers": {"1": "Raid tier 1: Barrow Deeps, Hyjal Summit, Onyxia's Lair"},
  "tier_notes": {"1": "Raids open 9 Dec 2026. Loot is from datamined data and may change."} }
```
`frontend/data/gear/<class>.<spec>.<A|H>.json` — same keys as Era (`class, class_id, faction, items, profile, role, slots, spec, spec_name, weights`). Each `items[id]` adds **`uncertain: [str]`** and **`checks: {field: confirmed|single|conflict}`**; each source adds **`conflict: bool`** and, when true, **`conflict_reason: str`** (readable sentence, shown verbatim). Races: Skyborne is two races (95 High Order Skyborne, Alliance; 96 Windshaper Skyborne, Horde); each race in meta has `slug` (e.g. `high_order_skyborne`) and `classes`. Tier labels use the form `"Raid tier 1: …"` (text before the colon is the button). `slots[slot]` = list of `{level, tier, items: [[id, score], …]}` breakpoints (unchanged).

## 4. API (backend)

- `GET /api/health` → `{"status":"ok","game":"forever","has_api_key":bool}`
- `GET /api/character?region=&name=&surname=` → `CharacterResult`; `CharacterSummary` drops `realm`, adds `surname`, `ruleset` (name or null). Namespaces `profile-forever-{region}` / `static-forever-{region}` / `dynamic-forever-{region}`. Path `/profile/wow/character/{slug}` with `slug = f"{name}-{surname}".lower()` URL-encoded; sub-paths `/equipment`, `/specializations`, `/character-media` optional (media often 404 for hours).
  - 404 message: "Character not found. Forever characters show up from level 10, after logging out. Check first name, surname and region."
  - Specializations: parse Era shape (`specialization_groups[].specializations[].spent_points`) and tolerate other shapes (unknown → empty list, spec falls back to leveling spec with a reason).
- `POST /api/score` unchanged.
- `GET /api/realms` removed.

## 5. Work packages

| WP | Owner | Files (exclusive) | Done when |
|---|---|---|---|
| W1 Data acquisition | sub-agent | `scripts/data/fetch_*.py`, `parse_questie.py`, `parse_warcraftdb.py`, `parse_blizzard.py`, `_common.py`, `requirements-data.txt`, `data/raw/**` | Staging JSON for QuestieDB Forever + warcraftdb (+ Blizzard if key) for all candidate gear items, from cache; coverage report in `reports/sources.md` |
| W2 Hand tables | sub-agent | `data/forever/instances.json`, `classes.json` (races, combos, proficiencies), `rulesets` note | Every row has ≥ 2 sources or an `uncertain` reason; new dungeons + raids present with ids that W1/W3 can map npcs → instance |
| W3 Merge, weights, build | sub-agent (after W1, W2) | `merge.py`, `build_gear.py`, `validate.py`, `data/forever/{weights,effects,exclude,items,sources}.json`, `backend/app/scoring.py`, `reports/*`, `frontend/data/**` | 50 gear files + meta per §3; conflicts report; weights reviewed for Forever class changes with cited sources |
| W4 Backend | sub-agent | `backend/**`, `api/**`, `vercel.json`, `conftest.py`, `pyproject.toml`, `requirements.txt` | §4 implemented; tests pass with invented fixtures |
| W5 Frontend | sub-agent (after W3 sample) | `frontend/*.{html,js,css}`, `frontend/bg/**`, `scripts/verify.mjs` | Forever look; name+surname+region lookup; ruleset shown; Skyborne in manual mode; tier picker from meta; Uncertain badge + reasons; wowhead/forever links |
| W6 Docs + audit | orchestrator | `README.md`, `tasks/*` | Audit against this plan passes; README updated |

## 6. Acceptance (audit checklist)

1. `pytest` green; no real character names in fixtures.
2. Pipeline re-runs from cache without network (`fetch_*` skipped when cached).
3. Every gear item in the output has a source; spot-check 20 random items against warcraftdb by hand: stats/req level/source match.
4. Rule checks: no plate before 40 for warriors/paladins, no mail before 40 for hunters/shamans, faction-only quests filtered, raid items only in tier ≥ 1, new dungeons appear in level range.
5. Items with a conflict show the Uncertain badge with readable reasons; ≥ 1 real conflict example verified end to end.
6. Character lookup works against a mocked Forever API (unit test) and, if a key is available, a live character.
7. Page loads with no console errors; manual mode works without an API key; mobile width OK.
8. No Wowhead fetching anywhere in scripts.
9. No Era data left anywhere: `data/era/` deleted, every `frontend/data/` file regenerated from Forever sources, no code path reads or falls back to Era data (grep for `era` / `classic1x` is clean apart from docs history).

## 7. Phase 2: lessons from Pawn and GearQuest Forever (owner decisions, 2026-11-18)

Reviewed: Pawn (item scoring, upgrade arrows) and GearQuest Forever (closest competitor; owner finds its data often wrong, no sorting, weak filtering).
Our edge to keep: cross-checked sources, open "Uncertain", real sort/filter, works outside the game.

| # | Item | Decision | Where |
|---|---|---|---|
| P1 | Upgrade shown as **% over what you wear** | Do. Replaces the points delta in the gain column (not both). No worn item → "new". Score column unchanged. | frontend |
| P2 | **Unscored stats marker** | Do. Stats the scorer can't use (Blizzard `unknown_stats`, unparsed effects) go into `items[id].unscored: [str]`; page shows `*` next to the score with the stat names on hover/expand. | merge/build + frontend |
| P3 | Custom / imported stat weights (Pawn scale strings) | **Not now.** Data quality first; single user. | — |
| P4 | Play-style presets | **No.** Keep the "Get it from" filter as is. | — |
| P5 | **Item lookup** | Do. Own panel in the right column with a search bar: find an item, show which levels/slots it is best (or top 3) for in the current spec/faction, its score and source. Uses the loaded gear JSON. | frontend |
| P6 | **Random-enchant items** ("of the Bear" …) | Do, matching GearQuest: rank on the best suffix roll for the spec, note "random enchant: best roll shown" (and which roll). First check how the pipeline handles them today (likely skipped or scored on base stats only). Suffix tables must come from Forever sources. | pipeline + frontend note |
| P7 | **Set bonuses and use effects** | Do, as a **toggle**: "Raw stats" vs "Set bonuses and effects" (default: raw stats until values are reviewed). Set data: Blizzard `preview_item.set` (effects + required_count), cross-checked with ForeverDB GearSets.lua. Use effects (e.g. Manual Crowd Pummeler 9449 for druids) need a cited guide value per spec in `data/forever/effects.json`, like the retail site's guide-based picks; no guess values. Gear JSON carries both scores. | pipeline + scoring + frontend |
| P8 | **Weapon-type selector** | Do. Simple select of the weapon types the class can use; default "Best" (no restriction). Filters weapon slots, What to do next and Coming up. | frontend |
| P9 | **Richer source details** | Do. Quest chain position ("Quest 3 of 6: <name>", with the chain's first quest and level), crafting reagents with counts, vendor/NPC zone, drop zone. Sources: QuestieDB Forever quest chains (pre/next quest), warcraftdb `created-by` tabs, ForeverDB sources. Shown in the expanded row and What to do next. | pipeline + frontend |

Order: P2, P6, P9, P7 data (pipeline agent) in parallel with P1, P5, P8 (frontend agent); then wire the new fields (P2 marker, P6 note, P7 toggle, P9 details) into the page; rebuild, validate, pytest, verify.mjs, screenshots, push.
Output additions (gear JSON `items[id]`): `unscored: [str]`, `random_enchant: {suffix, note}`, `score_set` (score with set bonuses/effects, absent when equal), `set: {name, pieces, bonuses}`; source additions: `chain: {pos, len, first_id, first_name, first_level}`, `reagents: [[name, count, id]]`, `zone`.
