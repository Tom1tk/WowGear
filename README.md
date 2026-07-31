# WowGearBis

Compare a WoW character's equipped gear against the Icy Veins Best-in-Slot list and
get a ranked list of concrete actions to close the gap (farm a dungeon, kill a boss,
craft an item, catch up ilvl).

## Stack

- Backend: FastAPI (Python 3.11), httpx, BeautifulSoup
- Frontend: static HTML/JS/CSS served by FastAPI (no build step)

## Setup

1. Python 3.11+: `python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt`
2. Register at https://develop.battle.net (free, needs a Blizzard login)
3. Create a client (Game Data / client-credentials type) and copy ID + Secret into `.env`
   (see `.env.example`). Without a key the app runs but `/api/analyze` returns a
   friendly setup error.
4. Run from the project root:
   `.venv/bin/uvicorn backend.app.main:app --reload`
5. Open http://127.0.0.1:8000

## API

- `GET /api/health` — status + whether the Blizzard key is configured
- `GET /api/specs` — class/spec catalog with Icy Veins BiS slugs (drives the UI dropdown)
- `POST /api/analyze` — body `{region, realm, character, spec?}` (spec optional: auto-detected
  from the character's active specialization). Returns character summary, per-slot
  comparison (equipped vs BiS), and a ranked action list (max 10) plus Icy Veins farm tips.

## Tests

`.venv/bin/pytest` from the project root. Icy Veins parser tests run against a saved
fixture (`backend/tests/fixtures/brewmaster_bis.html`); Blizzard client tests use a
mock HTTP transport.

## Notes

- Icy Veins pages are fetched once per hour (cached). BiS item ilvls are taken from the
  page's stated max item level (e.g. 289); per-difficulty track mapping via `bonus=` ids
  is a best-effort label.
- Todo/plan: `tasks/todo.md`
