# Data sources (WoW Forever), fetched 2026-11-18 (PARTIAL: crawls running)

Decision: QuestieDB is NOT used. Its data/Forever ItemDB is byte-identical to Classic Era (conversion.json: converted Era baseline), which the no-Era rule forbids, even as a candidate filter. staging/questie.json and parse_questie.py are deleted.
Candidates: forever.warcraftdb.com item sitemap (24,758 ids) plus ForeverDB gear-finder ids; gear is decided from the node's item_class (Weapon/Armor, not Poor, required level <= 60).

| Source | Role | Notes |
|---|---|---|
| forever.warcraftdb.com (node, tooltip, source tabs) | stats, slot, sources with drop chance | ~2 req/s, resumable, cached in data/raw/warcraftdb/. Full crawl takes hours. |
| Blizzard static-forever-eu (static-1.60.1_70399-forever-eu) | independent stats/slot/level | 404 = missing, not conflict. Cached in data/raw/blizzard/. |
| ForeverDB.net addon GearSources.lua (GPL-3, credit "Data from ForeverDB.net") | gear ids, sources | 8,271 items; 2,307 carry Classic-labelled (k) sources: do not trust those. /api/ not used. |

Counts and overlap: regenerate after the crawls finish (parse_warcraftdb.py, parse_blizzard.py, parse_foreverdb.py); the numbers at the time of writing were incomplete. Known gaps: rating vs percent stat wording unconfirmed; merge.py/build_gear.py/validate.py (W3) still read questie.json and ERA.
Not used: wowhead, wago, QuestieDB.
