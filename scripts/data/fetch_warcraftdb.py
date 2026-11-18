"""Crawl forever.warcraftdb.com for every item that can be gear (source B).

robots.txt there says `User-agent: * / Allow: /`. We identify ourselves, stay at
<= 2 requests/s, retry 429/5xx with backoff and cache every raw response under
data/raw/warcraftdb/ (git-ignored). Cached responses are never re-fetched unless
--refresh. Resumable: just run it again.

Per item: node JSON (basics + list of source tabs) -> if it can be gear, the
tooltip JSON -> every non-empty source tab (all pages).

Candidates: all sitemap ids plus ForeverDB gear-finder ids (no QuestieDB: it is Era data);
gear is decided from the node's item_class.

    python scripts/data/parse_foreverdb.py          # needs data/raw/foreverdb/GearSources.lua
    python scripts/data/fetch_warcraftdb.py [--limit N] [--ids 1,2,3] [--refresh] [--no-tabs]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(__file__))
from _common import RAW  # noqa: E402

BASE = "https://forever.warcraftdb.com"
UA = "WowGearBot/1.0 (+https://github.com/Tom1tk/WowGear)"
MIN_INTERVAL = 0.5  # seconds between requests (2 req/s)
DIR = RAW / "warcraftdb"
GEAR_CLASSES = {"Weapon", "Armor"}
# Tabs that never say where an item comes from.
SKIP_TABS = {"screenshots", "comments", "same-model", "sets", "teaches", "reagent-for", "tool-for", "dressing-room", "model", "videos", "see-also", "icon", "changelog"}
MAX_REQ_LEVEL = 60


class Client:
    def __init__(self) -> None:
        self.http = httpx.Client(timeout=30, headers={"User-Agent": UA, "Accept": "application/json"})
        self.last = 0.0
        self.requests = 0

    def get(self, path: str):
        """Return parsed JSON, or {"_status": code} for a non-retryable HTTP error."""
        for attempt in range(7):
            wait = MIN_INTERVAL - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            self.requests += 1
            try:
                resp = self.http.get(BASE + path)
            except httpx.HTTPError as exc:
                print(f"  net error {path}: {exc}", flush=True)
                time.sleep(2 ** attempt)
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("retry-after", "")
                time.sleep(float(retry_after) if retry_after.isdigit() else 2 ** (attempt + 1))
                continue
            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError:
                    time.sleep(2 ** attempt)
                    continue
            return {"_status": resp.status_code}
        raise RuntimeError(f"giving up on {path}")


def cached(client: Client, path: str, file, refresh: bool):
    if file.exists() and not refresh:
        return json.loads(file.read_text(encoding="utf-8"))
    data = client.get(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return data


def sitemap_ids(client: Client, refresh: bool) -> list[int]:
    file = DIR / "sitemap_item.xml"
    if not file.exists() or refresh:
        resp = client.http.get(f"{BASE}/sitemap/item.xml")
        resp.raise_for_status()
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(resp.text, encoding="utf-8")
    return sorted({int(i) for i in re.findall(r"/data/item/(\d+)", file.read_text(encoding="utf-8"))})


def candidate_ids(sitemap: list[int]) -> list[int]:
    """Every sitemap item id plus ForeverDB gear-finder ids (is_gear_node filters later)."""
    from parse_foreverdb import parse_gear_sources
    text = (RAW / "foreverdb" / "GearSources.lua").read_text(encoding="utf-8")
    return sorted(set(sitemap) | set(parse_gear_sources(text)))


def is_gear_node(node: dict) -> bool:
    d = node.get("data") or {}
    return (d.get("item_class") in GEAR_CLASSES and d.get("quality") not in (None, "Poor")
            and (d.get("required_level") or 0) <= MAX_REQ_LEVEL)


def fetch_item(client: Client, item_id: int, refresh: bool, tabs: bool) -> str:
    node = cached(client, f"/api/data/node/item/{item_id}", DIR / "node" / f"{item_id}.json", refresh)
    if "_status" in node or not is_gear_node(node):
        return "skipped"
    cached(client, f"/api/v1/tooltip/item/{item_id}", DIR / "tooltip" / f"{item_id}.json", refresh)
    if tabs:
        for tab in node.get("tabs", []):
            slug = tab["slug"]
            if slug in SKIP_TABS or not tab.get("count"):
                continue
            page = 1
            while True:
                data = cached(client, f"/api/data/node/item/{item_id}/tab/{slug}?page={page}",
                              DIR / "tab" / str(item_id) / f"{slug}_{page}.json", refresh)
                if "_status" in data or page >= (data.get("pages") or 1):
                    break
                page += 1
    return "gear"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="only process the first N candidates")
    parser.add_argument("--ids", help="comma separated item ids (overrides the candidate list)")
    parser.add_argument("--refresh", action="store_true", help="re-fetch cached responses")
    parser.add_argument("--no-tabs", action="store_true")
    parser.add_argument("--shuffle-seed", type=int, help="process candidates in a random order (sampling)")
    args = parser.parse_args()

    client = Client()
    if args.ids:
        todo = [int(i) for i in args.ids.split(",")]
    else:
        ids = sitemap_ids(client, args.refresh)
        todo = candidate_ids(ids)
        print(f"sitemap {len(ids)} ids; {len(todo)} candidates", flush=True)
    if args.shuffle_seed is not None:
        import random
        random.Random(args.shuffle_seed).shuffle(todo)
    if args.limit:
        todo = todo[: args.limit]
    stats = {"gear": 0, "skipped": 0}
    start = time.monotonic()
    for n, item_id in enumerate(todo, 1):
        stats[fetch_item(client, item_id, args.refresh, not args.no_tabs)] += 1
        if n % 100 == 0 or n == len(todo):
            rate = client.requests / max(time.monotonic() - start, 1)
            print(f"{n}/{len(todo)} gear={stats['gear']} skipped={stats['skipped']} "
                  f"requests={client.requests} ({rate:.2f}/s)", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
