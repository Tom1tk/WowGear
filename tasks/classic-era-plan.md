# Plan: reshape WowGearBis for WoW Classic Era (then WoW Forever)

Status: DRAFT — for review. No code changes yet.
Date: 2026-09-24

## 1. Goal

Change the app from Retail (Midnight S2) to **WoW Classic Era**.

**Core feature: BiS per level bracket.** For each class + role, show the best
gear at level **10, 20, 30, 40, 50 and 60**. At 60 there are more phases:
pre-raid, then raid tiers up to Naxxramas. The app reads the character's level
and gear, picks the right bracket, compares, and gives a ranked list of actions
("At 24, run Scarlet Monastery Armory for X"). It also shows the next bracket,
so the player can plan ahead.

Prepare the code for **World of Warcraft: Forever** ("Classic+"). Blizzard
announced it at BlizzCon 2026. Launch date: **4 November 2026**. It uses Classic
(level 1-60) as a base, with new zones, 9 new dungeons, 2 new max-level raids,
a new race (Skyborne) and new race/class pairs (Forsaken Paladin, Dwarf Shaman).
The API namespace, armory URL and Icy Veins URLs for Forever are not known yet.

## 2. Branch strategy

- Make a new long-lived branch `classic` from `main` (commit `fc0104e`).
- Do all Classic work on `classic`. Keep `main` as the frozen Retail version.
- Tag the current Retail state as `retail-final` before the work starts, so it
  is easy to find later.
- When Classic works end to end, decide: (a) make `classic` the new `main`, or
  (b) keep two branches. Recommendation: (a). You no longer play Retail, and
  one branch is easier to maintain.
- Vercel: point production at `classic` (or at `main` after the swap).

## 3. What changes, and why

### 3.1 Game "flavor" layer (new)

Retail values are hard-coded in many files. Classic Era and Forever share most
logic but differ in data. Add one small module `backend/app/flavor.py` with a
`Flavor` record per game:

| Field | Classic Era | Forever (placeholder) |
|---|---|---|
| `profile_namespace` | `profile-classic1x-{region}` | TBD |
| `dynamic_namespace` | `dynamic-classic1x-{region}` | TBD |
| `static_namespace` | `static-classic1x-{region}` | TBD |
| `icyveins_base` | `https://www.icy-veins.com/wow-classic/` | TBD |
| `wowhead_base` | `https://www.wowhead.com/classic/` | TBD |
| `armory_path` | TBD (verify, see 5) | TBD |
| `max_level` | 60 | 60 (verify) |
| spec catalog, drop-source catalog, progression bands | Era data files | Forever data files |

The request gets a `flavor` field (default `era`). All modules read values from
the flavor, not from constants. Result: Forever support = new data, not new code.

### 3.2 Character data — `blizzard.py`, `armory.py`

- Use the `classic1x` namespaces for Era. (Blizzard: Era realms use
  `classic1x-{region}`; Progression realms use `classic-{region}`.)
- Endpoints stay the same paths: `/profile/wow/character/{realm}/{name}` and
  `/equipment`. Forum reports say some Classic endpoints give 403/404. **Test
  this first** (step M0) with a real Era character.
- Realm list: `/data/wow/realm/index` with `dynamic-classic1x-{region}`.
  Era has few realms, so we can also keep a static list as a fallback.
- Slot map: add `RANGED` -> `ranged` (bows, guns, wands, thrown, relics:
  libram / idol / totem). Ignore `SHIRT` and `TABARD`.
- Summary: remove `mythic_plus_rating`. Keep level, race, class, guild.
  Optional: PvP rank / honor if the API gives it.
- Armory fallback: the Retail armory JSON (`characterProfileInitialState`) may
  not exist for Era. Verify. If it does not exist, drop the fallback for Era and
  require an API key.

### 3.3 Specs → roles — `specs.py`

Classic has no fixed specialization. A character spends talent points in three
trees. Icy Veins Classic BiS pages are **per class + role**, for example:

- `wow-classic/warrior-dps-pve-gear-best-in-slot`
- `wow-classic/warrior-tank-pve-gear-best-in-slot`
- also pre-raid pages, e.g. `wow-classic/warrior-dps-pre-raid-gear`

Changes:
- Replace `SPECS_BY_CLASS` with a class → roles catalog (and the pre-raid slug
  per role). Remove Death Knight, Monk, Demon Hunter, Evoker.
- Auto-detect: if the API gives talent points per tree, pick the role from the
  tree with most points (e.g. Protection → tank). Else the user picks a role in
  the UI.
- Rewrite `test_specs.py` (slug registry test) for the new slugs.

### 3.4 BiS parser — `icyveins.py`

- Save new fixtures from 2–3 Classic pages (e.g. warrior DPS, priest healer,
  hunter). Check the HTML. It may use the same `bis_item` grid or plain tables.
- Remove Retail parts: bonus-id → track map, "max item level" text, Catalyst
  and crest links.
- Keep: slot label, item id, item name, drop text + links, farm tips.
- Add: a phase / list selector if the page has more than one list
  (Pre-raid, Naxxramas / Phase 6).
- New slot aliases: Ranged, Wand, Relic, Libram, Idol, Totem.

### 3.5 Recommendation engine — `recommend.py` (largest change)

Item level is a weak signal in Classic. An ilvl 66 item can be worse than an
ilvl 60 item. So:

- **Gap metric**: "BiS item equipped" = match. Else = upgrade needed. Rank by
  slot weight and by how hard the source is (world drop / dungeon < 20-man
  raid < 40-man raid < Naxxramas). Show the ilvl only as information.
- Optional later: a simple stat-weight score per role to tell "close to BiS"
  from "far from BiS".
- **Action templates** per source type:
  - Dungeon: "Run Stratholme (Undead side) — Baron Rivendare drops X."
  - Raid: "Kill Ragnaros in Molten Core" (+ attunement note if needed:
    Molten Core, Onyxia, Blackwing Lair, Naxxramas).
  - Reputation: "Reach Exalted with Argent Dawn to buy X."
  - Crafted: "Craft / buy X (Blacksmithing). Note: BoP — you must craft it."
  - Quest reward, world boss, PvP rank reward, AQ gates / ZG tokens.
- **Remove** all Retail text: `UPGRADE_GUIDANCE`, crests, Catalyst, Great
  Vault, Mythic+, track ladder, Silvermoon vendors, Showdown zones.
- **Catch-up** by progression, not by ilvl bands:
  1. Below level 60 → use the level-bracket BiS (see 3.6).
  2. Level 60, mostly green/blue → pre-raid BiS list (dungeons, quests, rep).
  3. Pre-raid done → Molten Core / Onyxia / ZG / AQ20.
  4. Then BWL → AQ40 → Naxxramas.
  The stage comes from item quality and from which raid items are equipped.
- **Two-hand rule** stays (off-hand advice off with a 2H weapon).

### 3.6 Level-bracket BiS (core feature, new)

**Problem:** No single site gives a machine-readable BiS list per class + role
per level bracket. Icy Veins and Wowhead cover level 60 (pre-raid and raid
phases) well. Leveling gear is in free text guides (Noob to Boss, Overgear,
Wowhead leveling guides), in different formats, and not for every class/role.

**Plan: compute the brackets ourselves, offline, and commit the result.**

1. **Item database.** Build a local item table for Era: id, name, quality,
   required level, slot, armor/weapon type, stats, class limits, faction, bind
   type, and source (quest, dungeon + boss, world drop, vendor, crafted,
   reputation). Candidate sources, to check in M0:
   - Blizzard Game Data API, `static-classic1x-{region}` item endpoints
     (item + item search).
   - Wowhead Classic item data / tooltips (for source and drop info).
   - An open Classic item dataset (license must allow use).
2. **Stat weights per class + role** (e.g. warrior DPS: STR, AGI, crit, hit;
   priest heal: +healing, INT, SPI, MP5). Keep them in one data file so you
   can tune them. Weights may differ per bracket (e.g. hit matters less at 20).
3. **Rules per bracket:**
   - Required level <= bracket level.
   - Class can use the armor/weapon type (e.g. warrior may wear plate only from
     40; hunters/shamans get mail at 40).
   - Obtainable: filter out removed items, the other faction's items, and
     raid items below 60. Allow dungeons whose level range fits the bracket
     (Deadmines ~18, Scarlet Monastery ~30-40, Zul'Farrak ~45, BRD ~55).
   - Prefer easy sources when scores are close (quest reward > dungeon > rare
     world drop). Show a "realistic" pick and a "best" pick if they differ.
4. **Output:** `backend/app/data/era/brackets/{class}-{role}.json`, with one
   list per bracket (10, 20, 30, 40, 50, 60-pre-raid). Level 60 raid phases
   still come from Icy Veins (parsed), because curated raid BiS beats a
   computed one.
5. **Script:** `scripts/build_brackets.py`. Run it by hand when data or
   weights change. The web app only reads the JSON, so it stays fast.
6. **Check quality:** compare the computed lists with 2–3 human leveling
   guides for a few classes. Fix weights when results look wrong.

**How the app uses brackets:**
- Current bracket = highest bracket <= character level (level 27 → bracket
  20 gear is the "should have", bracket 30 is "next").
- Per-slot compare: equipped vs bracket BiS. Match / upgrade / empty.
- Actions: "You are 27. Run Scarlet Monastery Graveyard (26-36): Bloodmage
  Thalnos drops X." Sort by slot weight and by source ease.
- A bracket picker in the UI lets the player look at any bracket, also for
  alts or for planning.

### 3.7 Frontend — `frontend/`

- Remove Midnight S2 theme, key art and the "Upgrading & currencies" panel.
- New Classic look (parchment / gold). Use only art we are allowed to use.
- Form: region, realm (Era list), character, role picker (not spec picker),
  bracket picker (10/20/30/40/50/60 pre-raid/60 raid phases; default = from
  character level).
- Table: 17 slots (add Ranged/Relic). Show item quality color. ilvl column
  becomes secondary.
- New "Progression" panel: current stage + attunement checklist.
- Item links go to `wowhead.com/classic`.

### 3.8 Config, docs, deploy

- `config.py`: remove `bis_max_ilvl`. Add `default_flavor = "era"`.
- `README.md`, `tasks/todo.md`: rewrite for Classic.
- Keep Vercel setup. No change to `vercel.json` expected.

## 4. Milestones

| # | Work | Done when |
|---|---|---|
| M0 | Spike: find an item data source with stats + drop sources; test Era API (`classic1x`) profile + equipment with a real character; test Era armory page; save 3 Icy Veins Classic fixtures. | We know which data sources work. Go / no-go for armory fallback. |
| M1 | Branch `classic`, tag `retail-final`, add `flavor.py`, move constants into Era flavor. | Retail tests still pass with flavor = retail (or are removed in one step). |
| M2 | Blizzard client + slot map for Era. Mocked tests. | Tests pass for Era JSON fixtures. |
| M3 | Class/role catalog + Icy Veins Classic parser + fixture tests. | All slots parsed from fixtures. |
| M3b | Item database + stat weights + `build_brackets.py`; generate bracket JSON for all class/role pairs; spot-check against leveling guides. | Bracket lists look right for warrior, mage, priest, hunter. |
| M4 | New recommendation engine (bracket-aware) (match/upgrade, source ranking, action templates, progression catch-up). | Unit tests for each source type and each stage. |
| M5 | Frontend reskin + role picker + progression panel. | Manual run with a live Era character. |
| M6 | Docs + deploy on Vercel from `classic`. | Live site shows Era results. |
| M7 | Forever flavor (after 4 Nov 2026): namespaces, new race/class pairs, new dungeons and raids, Icy Veins URLs. | Forever character gives a result. |

Estimate: M0–M6 is about the same size as the first Retail build.
`recommend.py` and the frontend are the biggest parts.

## 5. Risks and open questions

1. **Bracket data quality.** Computed lists depend on stat weights and on
   good source data (which boss drops what). This is the biggest new risk.
   M0 must find an item data source with drop sources.
2. **Classic API gaps.** Some Classic profile endpoints return 403/404 (forum
   reports). If equipment is not available for Era, we need a different source
   (armory scrape, or a user paste from an addon export). M0 answers this.
3. **Armory for Era.** Unknown if the public armory has Era character pages
   with embedded JSON.
4. **Icy Veins HTML.** Classic pages may use a different layout than Retail.
5. **Forever unknowns.** Namespace, armory, guide sites, and whether Forever
   uses item level more (new systems) are unknown until launch. The flavor
   layer keeps this cheap.
6. **Hardcore / Anniversary realms.** Decide if we support them. They may use
   different namespaces or realm lists.
7. **Role detection.** Depends on talent data in the Era API.

## 6. Decisions needed from you

1. Branch name: `classic` OK? Make it the new `main` later (recommended)?
2. Keep Retail support in the flavor layer, or delete Retail code on the new
   branch? Recommendation: delete it. Less code, and the `retail-final` tag
   keeps it.
3. Support Hardcore / Anniversary realms, or Era only at first?
4. Level brackets: are 10/20/30/40/50/60 the right steps, or do you want
   smaller steps (e.g. every 5 levels)? Computed lists make any step cheap.
5. Keyless mode: is an API key required OK for Classic, if the armory
   fallback does not work?

## Sources

- WoW Forever announcement: https://blizzardwatch.com/2026/09/12/world-warcraft-forever-long-speculated-classic-plus-unveiled-will-launch-worldwide-november-4-2026/
- WoW Forever details: https://www.warcrafttavern.com/forever/news/warcraft-forever-classic-announced-at-blizzcon-2026/
- Era namespace (`classic1x`): https://us.forums.blizzard.com/en/blizzard/t/wow-classic-era-realm-apis/16812
- Classic endpoint 403/404 reports: https://us.forums.blizzard.com/en/blizzard/t/403-404-classic-classic1x/53959
- Leveling gear guides (for spot checks): https://noobtoboss.com/guides/wow-classic/class-guides/ , https://overgear.com/guides/wow-classic/best-way-of-gearing/
- Icy Veins Classic BiS example: https://www.icy-veins.com/wow-classic/warrior-dps-pve-gear-best-in-slot
