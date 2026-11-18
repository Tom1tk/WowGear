"""Fetch candidate gear items from the Blizzard Game Data API (WoW Forever, source C).

Namespace static-forever-{region}. Needs BLIZZARD_CLIENT_ID / BLIZZARD_CLIENT_SECRET
in .env; without them this prints a message and exits 0. About 40 % of ids are 404
in Forever: that is stored as a {"_status": 404} marker ("missing", not a conflict).
Raw responses are cached under data/raw/blizzard/items/ (git-ignored); re-runs only
fetch what is missing (--refresh to redo). Candidate ids = the same list as
fetch_warcraftdb.py (sitemap + ForeverDB ids).

    python scripts/data/fetch_blizzard_items.py [--region eu] [--limit N] [--refresh]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(__file__))
from _common import RAW, load_env, write_json  # noqa: E402
from fetch_warcraftdb import DIR as WDB_DIR, candidate_ids as _candidates  # noqa: E402

TOKEN_URL = "https://oauth.battle.net/token"
MAX_RPS = 40  # Blizzard allows 100/s; stay well under 50/s


async def token(client: httpx.AsyncClient) -> str:
    resp = await client.post(
        TOKEN_URL, auth=(os.environ["BLIZZARD_CLIENT_ID"], os.environ["BLIZZARD_CLIENT_SECRET"]),
        data={"grant_type": "client_credentials"},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def candidate_ids() -> list[int]:
    sitemap = WDB_DIR / "sitemap_item.xml"
    if not sitemap.exists():
        sys.exit("data/raw/warcraftdb/sitemap_item.xml missing: run fetch_warcraftdb.py first")
    ids = {int(i) for i in re.findall(r"/data/item/(\d+)", sitemap.read_text(encoding="utf-8"))}
    return _candidates(sorted(ids))


class Limiter:
    def __init__(self, rps: float) -> None:
        self.interval, self.next, self.lock = 1 / rps, 0.0, asyncio.Lock()

    async def wait(self) -> None:
        async with self.lock:
            now = time.monotonic()
            self.next = max(self.next, now) + self.interval
            delay = self.next - self.interval - now
        if delay > 0:
            await asyncio.sleep(delay)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="eu")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    load_env()
    if not (os.environ.get("BLIZZARD_CLIENT_ID") and os.environ.get("BLIZZARD_CLIENT_SECRET")):
        print("No BLIZZARD_CLIENT_ID / BLIZZARD_CLIENT_SECRET in .env: skipping Blizzard fetch.")
        return
    region = args.region
    raw_dir = RAW / "blizzard" / "items"
    raw_dir.mkdir(parents=True, exist_ok=True)
    ids = candidate_ids()[: args.limit or None]
    wanted = [i for i in ids if args.refresh or not (raw_dir / f"{i}.json").exists()]
    print(f"{len(ids)} candidates, {len(wanted)} to fetch ({region})", flush=True)
    limiter, sem, done = Limiter(MAX_RPS), asyncio.Semaphore(16), 0
    versions: dict[str, int] = {}

    async with httpx.AsyncClient(timeout=30) as client:
        headers = {"Authorization": f"Bearer {await token(client)}"}

        async def fetch(item_id: int) -> None:
            nonlocal done
            url = f"https://{region}.api.blizzard.com/data/wow/item/{item_id}"
            params = {"namespace": f"static-forever-{region}", "locale": "en_US"}
            async with sem:
                for attempt in range(6):
                    await limiter.wait()
                    try:
                        resp = await client.get(url, params=params, headers=headers)
                    except httpx.HTTPError:
                        await asyncio.sleep(1 + attempt)
                        continue
                    if resp.status_code in (429,) or resp.status_code >= 500:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    break
                else:
                    return  # not cached -> retried on the next run
            if resp.status_code == 200:
                text = resp.text
                m = re.search(r"static-([\w.\-]+)-forever", text)
                if m:
                    versions[m.group(1)] = versions.get(m.group(1), 0) + 1
            elif resp.status_code in (403, 401):
                raise SystemExit(f"Blizzard auth problem (HTTP {resp.status_code}); stopping")
            else:
                text = json.dumps({"_status": resp.status_code})
            (raw_dir / f"{item_id}.json").write_text(text, encoding="utf-8")
            done += 1
            if done % 1000 == 0:
                print(f"{done}/{len(wanted)}", flush=True)

        await asyncio.gather(*(fetch(i) for i in wanted))
    if versions:
        meta = RAW / "blizzard" / "version.json"
        write_json(meta, {"region": region, "namespace_versions_seen": versions,
                          "fetched": time.strftime("%Y-%m-%d")})
    print("done", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
