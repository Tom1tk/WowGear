"""Fetch every equippable Classic Era item from the Blizzard Game Data API.

Source A (reference for current Era values). Needs BLIZZARD_CLIENT_ID /
BLIZZARD_CLIENT_SECRET in .env. Raw responses are cached under
data/raw/blizzard/ (git-ignored); re-runs only fetch what is missing.

    python scripts/data/fetch_blizzard_items.py [--region us]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(__file__))
from _common import RAW, load_env, write_json  # noqa: E402

TOKEN_URL = "https://oauth.battle.net/token"
MIN_QUALITY = {"UNCOMMON", "RARE", "EPIC", "LEGENDARY"}


async def token(client: httpx.AsyncClient) -> str:
    resp = await client.post(
        TOKEN_URL,
        auth=(os.environ["BLIZZARD_CLIENT_ID"], os.environ["BLIZZARD_CLIENT_SECRET"]),
        data={"grant_type": "client_credentials"},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


async def get(client, url, params, headers, tries=5):
    for attempt in range(tries):
        try:
            resp = await client.get(url, params=params, headers=headers)
        except httpx.HTTPError:
            await asyncio.sleep(1 + attempt)
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            await asyncio.sleep(1 + attempt)
            continue
        return resp
    raise RuntimeError(f"giving up on {url}")


async def search_index(client, region, headers) -> list[dict]:
    """All items via the search endpoint, paged by id."""
    url = f"https://{region}.api.blizzard.com/data/wow/search/item"
    out: list[dict] = []
    last = 0
    while True:
        params = {
            "namespace": f"static-classic1x-{region}", "orderby": "id",
            "_pageSize": 1000, "_page": 1, "id": f"[{last + 1},]",
        }
        resp = await get(client, url, params, headers)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            break
        for row in results:
            data = row["data"]
            out.append({
                "id": data["id"],
                "equippable": data.get("is_equippable", False),
                "quality": (data.get("quality") or {}).get("type"),
                "required_level": data.get("required_level", 0),
                "level": data.get("level", 0),
            })
        last = results[-1]["data"]["id"]
        print(f"index: {len(out)} items (last id {last})", flush=True)
    return out


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="us")
    args = parser.parse_args()
    load_env()
    region = args.region
    raw_dir = RAW / "blizzard" / "items"
    raw_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=30) as client:
        headers = {"Authorization": f"Bearer {await token(client)}"}
        index_path = RAW / "blizzard" / "index.json"
        if index_path.exists():
            index = json.loads(index_path.read_text())
        else:
            index = await search_index(client, region, headers)
            write_json(index_path, index, compact=True)
        wanted = [
            row["id"] for row in index
            if row["equippable"] and row["quality"] in MIN_QUALITY
            and not (raw_dir / f"{row['id']}.json").exists()
        ]
        print(f"{len(index)} indexed, {len(wanted)} item details to fetch", flush=True)
        sem = asyncio.Semaphore(16)
        done = 0

        async def fetch(item_id: int) -> None:
            nonlocal done
            async with sem:
                resp = await get(
                    client, f"https://{region}.api.blizzard.com/data/wow/item/{item_id}",
                    {"namespace": f"static-classic1x-{region}", "locale": "en_US"}, headers,
                )
            if resp.status_code == 200:
                (raw_dir / f"{item_id}.json").write_text(resp.text, encoding="utf-8")
            done += 1
            if done % 500 == 0:
                print(f"details: {done}/{len(wanted)}", flush=True)

        await asyncio.gather(*(fetch(i) for i in wanted))
    print("done", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
