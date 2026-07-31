# Lessons Learned

## Blizzard API (2026-07-31)
- **Profile endpoints require the `namespace` param.** Requests to
  `eu.api.blizzard.com/profile/wow/...` WITHOUT `namespace=profile-eu` are
  rejected with `403 BLZWEBAPI00000403 {"detail":"Forbidden"}` — the same 403
  you'd otherwise blame on throttling/key issues. A request with the namespace
  succeeds seconds later. ALWAYS pass `profile-{region}` (characters) /
  `static-{region}` (media) — never `namespace=None`.
- Debugging discipline: when the app 403s but a curl probe succeeds, the
  difference is in the app's request. A/B-test the exact code path in one
  process (real method vs. raw mirror) until the difference is found — here
  the raw mirror had a `namespace` param the real calls lacked.
- The API now requires `Authorization: Bearer <token>`; the legacy
  `access_token=` query param returns an empty 404.
- Item names come from top-level `equipped_items[].name`, not `item.name`.
- Mythic+ rating is a float; round to int.
- Icy Veins data: `div.bis_item` grid, `data-wowhead="item=N&bonus=..."`,
  positional Ring/Trinket, drop links/texts, JSON-LD FAQ farm tips, max ilvl 289.

## General
- When a "server only" failure persists after restarts, verify the process
  actually restarted with the new code (cwd/`--app-dir` matter for uvicorn).
- Keep raw A/B probes byte-identical to the code under test; any extra param
  invalidates the comparison.
