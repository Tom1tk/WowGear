# Plan: reshape WowGearBis for WoW Classic Era

Status: v3 — implemented on branch `classic-era` (see tasks/todo.md for progress).
Change after review: levels use a **slider for every level 10–60** (owner request) instead of 10-level brackets.
Date: 2026-09-24

## 0. Decisions (from review)

| Topic | Decision |
|---|---|
| Branch | `classic-era`, made from `main` (`fc0104e`). |
| Retail | Tag current `main` as `retail-final`. Do not maintain it. It goes out of date and is phased out when Classic Era is done. Remove Retail code on `classic-era`. |
| Game scope | Classic Era realms only. No Hardcore, Anniversary, Season of Discovery or WoW Forever for now. Forever will need a new review when it launches (4 Nov 2026). |
| Brackets | Steps of 10: **10-19, 20-29, 30-39, 40-49, 50-59, 60**. Items fall into a bracket by required level (a great level-12 item is in 10-19). Start at 10; levels 1-9 are vendor and quest gear. |
| No API key / no armory | Manual mode: the user enters race, class, spec and level. The site works out the rest. |
| Data | Many sources, cross-referenced. The owner is a new Classic player: the site must not depend on the owner's game knowledge to be correct. |

## 1. Goal

A new Classic Era player enters a character (or picks race / class / spec /
level). The site shows:

1. **The BiS gear for the current level bracket**, per slot, with where to get
   each item and at which level it can be used.
2. **What to do next**: a short ranked list ("At 24, run Scarlet Monastery
   Graveyard: Bloodmage Thalnos drops X").
3. **The next bracket**, so the player can plan.
4. At level 60: pre-raid BiS, then raid phases (Molten Core → Naxxramas).

The site explains Classic terms in plain words (BoP, BoE, attunement, quest
chain), because the target user is new to Classic.

## 2. Branch and repo strategy

1. Tag `main` as `retail-final` and push the tag.
2. Create `classic-era` from `main`.
3. On `classic-era`: remove Retail-only code and content (Midnight theme,
   crests / Great Vault / Catalyst text, retail spec slugs, retail fixtures).
   Keep the parts that still fit: FastAPI app, Blizzard client base, Icy Veins
   fetch/cache, text-segment links, frontend structure, Vercel setup.
4. Keep game data in `data/era/`. If Forever is added later, it gets its own
   `data/forever/` folder. No generic "flavor" framework now (YAGNI).
5. When `classic-era` is live and good, make it the new `main`.

## 3. How a bracket works

- Bracket **N** (e.g. 20-29) holds items with required level N to N+9.
- One bracket list is a **gear path per slot**, not one item per slot. For
  example, for "Chest, 20-29":
  - Lvl 21: item A (quest, Alliance, Westfall)
  - Lvl 26: item B (Scarlet Monastery Graveyard; better than A)
  - Lvl 28: item C (BoE world drop, Auction House; best, rare)
- The site shows which of these the character can use **now** and which come
  **later** in the bracket. The last good item in each slot is the "bracket
  BiS".
- An item from an earlier bracket stays valid until a better item replaces it.
  So a slot in 30-39 can show "keep your level-27 item until level 34".
- Bracket **60** has sub-lists: *Pre-raid* (dungeons, quests, reputation,
  crafted), then *Molten Core / Onyxia*, *Blackwing Lair / ZG*, *AQ*,
  *Naxxramas*.

## 4. What changes in race / class / spec

- **Class** decides armor and weapon types. Some change at level 40
  (warriors and paladins learn plate; hunters and shamans learn mail).
  The builder must know this, so a level-35 warrior does not get a plate item.
- **Spec** decides stat weights. Leveling and raiding often use a different
  spec (e.g. many priests level as Shadow and heal at 60). So a spec can have
  separate "leveling" and "level 60" weights.
- **Race** decides:
  - **Faction** (Alliance / Horde): many quests and some vendors are for one
    faction only.
  - **Starting zones and typical leveling route**: quest rewards in the
    player's zones are more realistic than quests on the other continent.
  - **Racial weapon skills** (e.g. Human: swords, maces; Orc: axes). These
    change which weapon is best for some classes.

## 5. Data: what we need

| Dataset | Content | Use |
|---|---|---|
| Items | id, name, quality, required level, slot, armor/weapon type, stats, weapon speed/DPS, class limit, faction, bind type (BoP/BoE), unique, set | Scoring and rules |
| Sources | per item: drop (boss/creature, dungeon/zone, drop chance), quest reward (quest, level, faction, zone, chain), vendor (NPC, cost, reputation), crafted (profession, skill), world drop | "Where to get it" + realism |
| Quests | id, level, faction, zone, start NPC, chain, reward choices | Quest-reward sources |
| Dungeons / raids | name, level range, zone, faction side, wings, attunement | Bracket fit + action text |
| Stat weights | per class + spec + (leveling / 60) | Scoring |
| Class rules | armor/weapon proficiency by level, racial skills | Rules |
| Reference BiS lists | human-made lists per class/spec/bracket | Validation |

## 6. Data: sources and cross-reference

Rule: **every fact gets its source(s) stored with it.** A fact is "confirmed"
when two independent sources agree. Else it is "single-source" or "conflict".
The site shows confirmed data normally and marks the others. Conflicts go to a
review report.

| Dataset | Primary | Cross-check | Notes |
|---|---|---|---|
| Item stats, req level, slot, type | Blizzard Game Data API, `static-classic1x-{region}` (item + item search) | Wowhead Classic item page; CMaNGOS `classic-db` | Blizzard API is the reference for current Era values. Forum reports say some Classic endpoints give 403/404 — test in M0. |
| Drop sources + drop chance | Wowhead Classic ("Dropped by", with %) | CMaNGOS / VMaNGOS loot tables | Emulator data is based on patch 1.12. Era changed some loot and stats, so emulator data is a cross-check, never the only source. |
| Quest rewards | Wowhead Classic quest pages | CMaNGOS / VMaNGOS quest tables | Faction and quest chain data needed. |
| Vendor / reputation / crafted | Wowhead Classic | CMaNGOS vendor + recipe tables | Mark BoP crafted items ("you must have the profession"). |
| Dungeon level ranges, attunements | Wowhead / Icy Veins dungeon guides | Warcraft Wiki | Small, hand-kept table; easy to check. |
| Stat weights | Icy Veins + Wowhead class guides | Class community guides (Discord / guide sites) | Store the source per weight set. Weights are the biggest judgement call. |
| Level-60 BiS | Icy Veins Classic BiS pages | Wowhead Classic BiS pages; wowisclassic.com | Parse and compare. Differences shown as "alternatives". |
| Leveling BiS (reference) | Noob to Boss class guides | Overgear, Wowhead leveling guides, EpicCarry | Used to **validate** the computed lists, not as the main data. |

**Rules for fetching:**
- Read each site's terms and `robots.txt` first. Prefer the Blizzard API and
  open data. Use Wowhead / guide sites only where allowed.
- Rate limit, cache all raw responses under `data/raw/` (git-ignored), and
  re-run from cache.
- Check licenses before we commit any derived data (CMaNGOS / VMaNGOS data
  licenses, guide-site content). Store facts (ids, numbers), not copied text.

## 7. Data pipeline (offline, in `scripts/data/`)

```
fetch_*.py   ->  data/raw/<source>/...          (cache, not committed)
normalize_*.py -> data/era/staging/<source>.json (one schema for all sources)
merge.py     ->  data/era/items.json, sources.json, quests.json,
                 dungeons.json  (+ provenance, confidence)
             ->  reports/conflicts.md
build_brackets.py -> data/era/brackets/<class>-<spec>.json
validate.py  ->  reports/validation.md  (compare with reference lists)
```

- Python, same toolchain as the backend. Each step can run alone.
- The web app only reads `data/era/*.json`. No scraping at request time
  (Icy Veins level-60 lists can be pre-fetched the same way).
- `validate.py` gives a score per class/spec/bracket: how many of the
  reference guide items are in our list, and which of our items no guide
  lists. Items only we pick get a manual check.

## 8. Bracket builder (`build_brackets.py`)

For each class, spec, faction and bracket:

1. **Candidates**: items with required level in the bracket (or lower and
   still good), usable by the class at that level, correct faction, source
   still in the game, source level fits the bracket (dungeon level range).
   No raid items below 60.
2. **Score** = sum(stat × weight) + weapon DPS term for weapons. Special
   "use/equip" effects: a small hand-kept table of extra values.
3. **Realism**: per source a difficulty/luck factor (quest reward: easy;
   dungeon boss: medium; rare world drop: hard / Auction House). Show a
   **best** pick and a **realistic** pick when they differ.
4. **Output** per slot: the gear path (section 3), each item with score,
   source, level, confidence, and provenance.
5. Two-hand vs one-hand + off-hand is compared as a pair.

## 9. Character input

Order of attempts:

1. **Blizzard API** (`profile-classic1x-{region}`): profile + equipment.
   Needs an API key. Test in M0.
2. **Armory page** (if Era character pages exist and embed data). Test in M0.
3. **Manual mode** (always available):
   - Enter race, class, spec, level (region/realm not needed).
   - The site shows the bracket gear path as a **checklist**. The user ticks
     the items they own. Ticks are kept in the browser (localStorage), so the
     list follows the player while they level.
   - Optional later: paste item links or an addon gear export to fill the
     checklist. Check which Era addons can export gear (research item).

Result for all three: the same internal "character + equipped items" model,
so the rest of the app does not care where the data came from.

## 10. App changes (by file)

- `blizzard.py`: `classic1x` namespaces; slot map adds `RANGED`
  (bow / gun / wand / thrown / libram / idol / totem); drop `SHIRT`, `TABARD`;
  remove Mythic+ rating.
- `armory.py`: keep only if M0 shows Era pages work; else delete.
- `specs.py`: class → specs (talent trees) → leveling / 60 weight sets, and
  Icy Veins Classic role slugs for level 60 (e.g.
  `wow-classic/warrior-dps-pve-gear-best-in-slot`). Nine classes only.
- `icyveins.py`: new parser + fixtures for Classic pages (level 60 only).
- `recommend.py`: rewrite. Item-based compare (not ilvl gap). Action text per
  source type: dungeon (with level range and wing), quest (with zone and
  faction), vendor / reputation, crafted (BoP note), Auction House (BoE),
  raid (with attunement at 60). Remove all Retail guidance text.
- `models.py`: add `ranged` slot, `Source` model with provenance and
  confidence, bracket models; remove track / bonus fields.
- `main.py`: new endpoints —
  `GET /api/classes` (races, classes, specs),
  `GET /api/brackets/{class}/{spec}?faction=&level=`,
  `POST /api/analyze` (character or manual input).
- `frontend/`: new Classic look; input form with "Look up character" and
  "Enter manually" tabs; bracket picker (10/20/30/40/50/60 + phases);
  per-slot gear path with "use now" / "later" marks; checklist; glossary
  tooltips; Wowhead Classic item links (`wowhead.com/classic/item=`);
  a "report a wrong item" link (GitHub issue) for user feedback.
- Tests: fixtures for Era API JSON, Icy Veins Classic pages, a small sample
  item set for the bracket builder (rule tests: plate at 40, faction filter,
  bracket edges 19/20, 2H vs 1H + OH).

## 11. Milestones

| # | Work | Done when |
|---|---|---|
| M0 | **Research spike.** Test Era API (profile, equipment, item, item search) with a key; test Era armory pages; check terms/licenses of each data source; save sample raw data from each. | A short report: which sources work, which we may use. |
| M1 | Tag `retail-final`, create `classic-era`, remove Retail code, set up `data/era/` and `scripts/data/`. | App starts; tests for kept code pass. |
| M2 | Static tables by hand: dungeons/raids with level ranges + attunements, class proficiency rules, racial skills. Each row with 2 sources. | Tables reviewed. |
| M3 | Item + source pipeline (fetch, normalize, merge, conflict report) for **one class** first (Warrior). | Conflict report is small and explained. |
| M4 | Stat weights for Warrior (leveling + 60) + bracket builder + validation report vs 2+ reference guides. | Validation looks good for all 6 brackets. |
| M5 | Manual-mode frontend (race/class/spec/level + checklist) using Warrior data. | **You** can use it for your own character and give feedback. |
| M6 | Extend the pipeline and weights to all 9 classes (one class at a time, each with its validation report). | All classes pass validation review. |
| M7 | Level 60: Icy Veins Classic parser + raid phases + attunement notes. | Pre-raid and raid lists show for all specs. |
| M8 | Character lookup (API / armory, from M0 results) + automatic compare. | Live Era character gives a result. |
| M9 | Docs, deploy on Vercel from `classic-era`, then make it `main`. | Live site. |

Why this order: manual mode (M5) does not need the API, so you can use the
site early. One class end to end first (M3-M5) finds problems before we
repeat the work nine times.

## 12. How we make it correct without a Classic expert

- Two-source rule for every fact (section 6).
- Validation reports against several human-made guides per bracket.
- Rule tests for known Classic facts (plate at 40, faction quests, etc.).
- You are the test user: each milestone ends with you trying it on your
  character. "This looks odd" feedback is valuable, even without deep
  knowledge.
- In-site "report a wrong item" link collects feedback from other players.

## 13. Risks and open questions

1. **Data access.** The Blizzard Classic API may not give all items or
   profiles (403/404 reports). Wowhead terms may limit automated fetching.
   M0 decides the real source mix.
2. **Stat weights.** These are the biggest judgement call. Mitigation:
   validation against guides, and store the source of each weight set.
3. **Era vs 1.12 differences.** Emulator databases are 1.12. Era has some
   changed items and loot. Always prefer Blizzard / Wowhead Classic values.
4. **Special effects** ("Chance on hit: ...") are hard to score. Start with a
   small hand-kept table for well-known items; flag others as "has effect".
5. **Size of work.** Nine classes × specs × 6 brackets × 2 factions. The
   pipeline makes this mostly automatic, but the validation review per class
   takes time.

## 14. Open questions for you

1. Which class/spec do you play? Recommendation: use it as the first class in
   M3-M5 instead of Warrior, so you can test with your own character.
2. Do you have a Blizzard API key (develop.battle.net) we can use for M0?
3. Is a GitHub-issue "report a wrong item" link OK, or do you want no public
   feedback channel at first?

## Sources

- WoW Forever announcement: https://blizzardwatch.com/2026/09/12/world-warcraft-forever-long-speculated-classic-plus-unveiled-will-launch-worldwide-november-4-2026/
- Era namespace (`classic1x`): https://us.forums.blizzard.com/en/blizzard/t/wow-classic-era-realm-apis/16812
- Classic endpoint 403/404 reports: https://us.forums.blizzard.com/en/blizzard/t/403-404-classic-classic1x/53959
- Classic item endpoint issue: https://us.forums.blizzard.com/en/blizzard/t/wow-classic-datawowitemitemid-results-in/56949
- CMaNGOS Classic DB: https://github.com/cmangos/classic-db
- VMaNGOS: https://github.com/vmangos
- Icy Veins Classic BiS example: https://www.icy-veins.com/wow-classic/warrior-dps-pve-gear-best-in-slot
- Wowhead Classic BiS: https://www.wowhead.com/classic/guide/wow-classic-bis-best-in-slot-gear-lists
- wowisclassic BiS: https://www.wowisclassic.com/en/best-in-slot/
- Leveling gear guides: https://noobtoboss.com/guides/wow-classic/class-guides/ , https://overgear.com/guides/wow-classic/best-way-of-gearing/ , https://epiccarry.com/blogs/wow-classic-anniversary-gear-guide/
