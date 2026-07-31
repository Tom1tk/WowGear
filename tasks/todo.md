# WowGearBis — Gear vs BiS recommendation app

Compare a WoW character's equipped gear against Icy Veins Best-in-Slot, then produce
a ranked list of 5–10 concrete actions to close the gap.

## Architecture

- **Backend**: FastAPI (Python 3.11+), `httpx` for HTTP, `BeautifulSoup` for Icy Veins scraping.
- **Frontend**: static HTML/JS/CSS served by FastAPI (no build step for MVP).
- **Data sources**:
  - Blizzard Game Data API (OAuth2 client-credentials) — character profile + equipment.
  - Icy Veins BiS page — per-slot BiS items, item IDs, drop locations (scraped).
- **Recommendations**: rule-based v1 (no ML).

## Components

### backend/app/blizzard.py
- `BlizzardClient`: token acquisition (`/oauth/token`), character profile summary
  (`/profile/wow/character/{realm}/{name}`), equipment
  (`/profile/wow/character/{realm}/{name}/equipment`).
- Region-aware base URL (us/eu/...), token cache with expiry, error mapping
  (404 = character not found, 401 = bad key).
- No key configured -> raise a clear, friendly error surfaced in the UI.

### backend/app/icyveins.py
- Parse `div.image_block_content#bis_0_0` (Overall BiS grid; optionally 0_1 M+ and 0_2 Raid).
- For each `div.bis_item`: slot label (`span.bis_item_slot`), item id + bonus track
  (`data-wowhead="item=NNN&bonus=..."`, unescape `&amp;`), item name (span with `class=qN`),
  drop source (`span.bis_item_drop`).
- Slot normalization: Helm->head, Bracers->wrist, Cloak->back, Main Hand/Off Hand, etc.
  Ring/Trinket are positional (2nd occurrence = ring2/trinket2).
- Bonus-id -> track mapping (13786 = mythic raid, 12806 = mythic+, etc.) -> BiS ilvl
  for gap math.
- Skip `bis_item--empty` blocks. Keep raw HTML fixture for tests.

### backend/app/recommend.py
Per-slot comparison (16 slots):
- Missing item (empty slot) = biggest gap.
- Same item id = match (no action).
- Different item: gap = BiS-track ilvl - equipped ilvl. Equipped >= BiS ilvl means
  "already comparable, skip" unless item is BiS-identical.
- Urgency score = ilvl deficit weighted by slot (weapon/trinket/chest/legs slightly higher).

Action templates (per item, using Icy Veins drop text when available):
- "Run {dungeon} (Mythic+) to get {item} from {boss}" when drop source is a dungeon.
- "Kill {boss} on {difficulty} in {raid}" for raid drops.
- "Craft {item} (profession recipe)" / "Buy {item} from the Auction House" for crafted.
- Catch-up rule: if avg ilvl below configurable threshold, prepend
  "Farm Heroic dungeons (Nagital/Val) for Champion/Hero-track gear" style advice.
- Output top 10 actions sorted by urgency; each action has: slot, target item,
  equipped vs BiS ilvl, action text, source.

### backend/app/main.py
- `POST /api/analyze` {region, realm, character, spec_url} -> {character, comparison, actions}.
- `GET /` serves frontend. Static files under `frontend/`.
- Caching: Blizzard token (in-memory TTL), BiS page HTML (TTL ~1h), per-key responses.

### frontend/
- Form: region (US/EU), realm slug, character name, spec picker (dropdown of
  class/spec -> Icy Veins BiS URL).
- Results: character summary card (name, realm, class, spec, ilvl, faction),
  slot-by-slot comparison table (equipped vs BiS, green/red deltas),
  ranked action list (numbered 1..10 with priority colors).

### backend/tests/
- `test_icyveins.py` — parse fixture HTML (saved copy of the brewmaster page):
  all 15 populated slots extracted, ring/trinket positional mapping, bonus unescape.
- `test_recommend.py` — synthetic equipment vs parsed BiS: match/missing/wrong-item
  cases, urgency ordering, action text generation.
- `test_blizzard.py` — mocked httpx: token flow, 404 mapping.

## Config / secrets

- `.env.example` -> copy to `.env`: `BLIZZARD_CLIENT_ID`, `BLIZZARD_CLIENT_SECRET`.
- No key = app still runs, analyze returns friendly "register at develop.battle.net" error.

## User setup steps (documented in README)

1. Register at https://develop.battle.net (free, Blizzard login).
2. Create a client (type "Game Data" / client credentials) -> Client ID + Secret.
3. Add to `.env`. Run `uvicorn app.main:app --reload`.

## Milestones

1. Scaffold: project layout, `.env.example`, README, FastAPI skeleton with /api/health.
2. Blizzard client (token + profile + equipment) with mocked tests.
3. Icy Veins parser + fixture + tests.
4. Recommendation engine + tests.
5. Frontend (form + comparison table + action list).
6. End-to-end local run with synthetic character data (no key needed), then live
   with user's key + Greyball/Draenor.

## Stretch (not in MVP)

- Armory HTML scrape as keyless fallback (we already proved it embeds full gear state).
- Mythic+ rating in recommendations ("push +N keys to get X from Great Vault").
- Per-track grids (M+/Raid tabs) selectable in UI.
- Auto-detect spec from character (talent loadout parse) instead of manual picker.

## Review (2026-07-31)

ALL milestones complete. Live test passed with Greyball/Draenor (EU) end-to-end:
armory fallback -> Icy Veins BiS parse -> 10 ranked actions with drop sources.

Findings:
- Blizzard API: OAuth token works, but ALL legacy endpoints on {region}.api.blizzard.com
  return 404 with empty body for this key (key likely not provisioned for WoW API on the
  new dev portal, or the public API surface changed). Armory embeds full API-shaped JSON
  (`characterProfileInitialState`) with gear/ilvl/spec/M+/stats — used as automatic fallback.
  TODO: check client "API Access" products at develop.battle.net; if enabled, BlizzardClient
  path should start working with zero code changes (404-with-JSON vs 404-empty distinguishes
  not-found from unavailable).
- Icy Veins structure verified against fixture: div.bis_item grid, data-wowhead="item=N&bonus=...",
  positional Ring/Trinket, drop text + guide links per item, FAQ JSON-LD farm tips, max ilvl 289.
- pytest-asyncio 1.4.0 does NOT intercept async tests in this env (anyio conflict / pytest 9);
  used asyncio.run() wrappers instead — keep tests plugin-independent.

Next steps (v2 candidates):
- Verify/fix Blizzard API provisioning; drop armory fallback or keep as resilience layer.
- Great Vault / M+ push advice (character.mythicKeystoneDungeons already available in armory state).
- Per-track BiS grids (M+/Raid tabs) selectable in UI.
- ilvl thresholds for catch-up advice tuned per season (heroic/champion track ilvls).

## Review update (2026-07-31, API fix)

Root cause of the API 404s: NOT the key — Blizzard now rejects the legacy
`access_token=` query parameter (empty 404) and requires
`Authorization: Bearer <token>` header on every request. Fixed in blizzard.py;
live test now uses `source: blizzard`. The armory fallback stays as a resilience
layer. Also fixed: equipment item names live at the top level of each equipped
item (not under `item.name`), and mythic+ rating is a float (rounded to int).
Doc requirements confirmed via portal JSON API: account needs Battle.net
Authenticator (2FA) + accepted Developer API ToU before requests.

## Review (2026-07-31)
- Fixed the final 403 bug: profile endpoints were called with `namespace=None`,
  and Blizzard now rejects nameless profile requests with
  `403 BLZWEBAPI00000403 Forbidden`. Passed `namespace=profile-{region}` for
  character/mythic+/media/equipment calls. Verified live: `/api/analyze` →
  `source: blizzard`, avatar+render URLs, 16/16 icons, all 29 tests pass.
- All prior "throttling / token flagged / 403 burst" conclusions were this same
  missing-namespace bug misdiagnosed. Comments in blizzard.py corrected.
- Server restarted with fix; lessons recorded in tasks/lessons.md.
