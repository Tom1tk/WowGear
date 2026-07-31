"""Blizzard Game Data API client (OAuth2 client credentials flow).

Note: the API now requires the token via `Authorization: Bearer` header —
the legacy `access_token=` query parameter is rejected with an empty 404.
"""

import asyncio
import base64
import json
import time
from pathlib import Path

import httpx

from .models import CharacterSummary, EquippedItem

TOKEN_URL = "https://oauth.battle.net/token"

# Item icons are immutable; persist them to disk so restarts don't re-fetch
# the same 16+ media requests per character (the API throttles bursts).
_ICON_CACHE_PATH = Path(__file__).resolve().parent / "item_icon_cache.json"
_ITEM_MEDIA_CACHE: dict[tuple[str, int], str | None] = {}

if _ICON_CACHE_PATH.exists():
    try:
        for key, value in json.loads(_ICON_CACHE_PATH.read_text(encoding="utf-8")).items():
            region, _, item_id = key.partition(":")
            _ITEM_MEDIA_CACHE[(region, int(item_id))] = value
    except (ValueError, json.JSONDecodeError, OSError):
        pass

SLOT_MAP = {
    "HEAD": "head",
    "NECK": "neck",
    "SHOULDER": "shoulders",
    "BACK": "back",
    "CHEST": "chest",
    "WRIST": "wrist",
    "HANDS": "hands",
    "WAIST": "waist",
    "LEGS": "legs",
    "FEET": "feet",
    "FINGER_1": "ring_1",
    "FINGER_2": "ring_2",
    "TRINKET_1": "trinket_1",
    "TRINKET_2": "trinket_2",
    "MAIN_HAND": "main_hand",
    "OFF_HAND": "off_hand",
}

# (region, item_id) -> icon URL; item icons are effectively immutable
_ITEM_MEDIA_CACHE: dict[tuple[str, int], str | None] = {}


class BlizzardError(Exception):
    """Base error for Blizzard API failures."""


class ApiKeyMissingError(BlizzardError):
    pass


class ApiKeyInvalidError(BlizzardError):
    pass


class CharacterNotFoundError(BlizzardError):
    pass


class RateLimitedError(BlizzardError):
    pass


class ApiUnavailableError(BlizzardError):
    """Raised when the API responds 404 with an empty body — i.e. the endpoint
    surface is not available for this client (unprovisioned key or API moved)
    rather than the resource being missing."""


class BlizzardClient:
    def __init__(self, client_id: str, client_secret: str, timeout: float = 15.0,
                 transport: httpx.AsyncBaseTransport | None = None,
                 cache_ttl_seconds: float = 600.0) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._timeout = timeout
        self._transport = transport
        self._cache_ttl = cache_ttl_seconds
        self._response_cache: dict[tuple, tuple[float, dict]] = {}

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._timeout, transport=self._transport)

    async def _get_token(self, client: httpx.AsyncClient) -> str:
        # NOTE: tokens are intentionally NOT cached. Blizzard flags access
        # tokens after heavy reuse and starts rejecting them with 403 —
        # minting a fresh token per request batch keeps the app reliable.
        auth = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        resp = await client.post(
            TOKEN_URL,
            headers={"Authorization": f"Basic {auth}"},
            data={"grant_type": "client_credentials"},
        )
        if resp.status_code == 401:
            raise ApiKeyInvalidError(
                "Blizzard API rejected the credentials (401). "
                "Check BLIZZARD_CLIENT_ID / BLIZZARD_CLIENT_SECRET in .env."
            )
        if resp.status_code != 200:
            raise BlizzardError(
                f"Blizzard OAuth token request failed with HTTP {resp.status_code}."
            )
        payload = resp.json()
        return payload["access_token"]

    async def _request(
        self, client: httpx.AsyncClient, region: str, path: str,
        namespace: str | None = None,
    ) -> dict:
        if not (self.client_id and self.client_secret):
            raise ApiKeyMissingError(
                "Blizzard API key is not configured. "
                "Register at https://develop.battle.net and add "
                "BLIZZARD_CLIENT_ID / BLIZZARD_CLIENT_SECRET to .env, then restart."
            )
        token = await self._get_token(client)
        params = {"locale": "en_US"}
        if namespace:
            params["namespace"] = namespace
        url = f"https://{region}.api.blizzard.com{path}"
        headers = {"Authorization": f"Bearer {token}"}

        for attempt in range(3):
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 429 and attempt < 2:
                # Real rate limit — back off and retry. Do NOT retry 403:
                # a 403 (BLZWEBAPI00000403) means a missing/wrong namespace
                # param, and retrying won't fix it.
                await asyncio.sleep(0.6 * (attempt + 1))
                continue
            break

        if resp.status_code == 404:
            if not resp.text.strip():
                raise ApiUnavailableError(
                    "The Blizzard API is not available for this client (all requests "
                    "return 404). Check that World of Warcraft API Access is enabled "
                    "for your client at develop.battle.net."
                )
            raise CharacterNotFoundError(f"Character not found for API path: {path}")
        if resp.status_code == 401:
            raise ApiKeyInvalidError(
                "Blizzard API rejected the key (401). "
                "Check BLIZZARD_CLIENT_ID / BLIZZARD_CLIENT_SECRET in .env."
            )
        if resp.status_code == 403:
            # 403 BLZWEBAPI00000403 means the request is missing/wrong
            # namespace or otherwise forbidden — surface as "API unavailable"
            # so callers can fall back to the Armory scraper.
            raise ApiUnavailableError(
                "The Blizzard API is rejecting requests (403 — check namespace "
                "params and API access). Fell back to the Armory for now."
            )
        if resp.status_code == 429:
            raise RateLimitedError("Blizzard API rate limit reached (429). Try again shortly.")
        if resp.status_code != 200:
            raise BlizzardError(
                f"Blizzard API request failed with HTTP {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json()

    async def _get(self, region: str, path: str, namespace: str | None = None) -> dict:
        key = (region, path, namespace)
        cached = self._response_cache.get(key)
        if cached and time.time() - cached[0] < self._cache_ttl:
            return cached[1]
        async with self._make_client() as client:
            data = await self._request(client, region, path, namespace)
        self._response_cache[key] = (time.time(), data)
        return data

    async def character_summary(self, region: str, realm: str, character: str) -> CharacterSummary:
        data = await self._get(
            region, f"/profile/wow/character/{realm}/{character}", namespace=f"profile-{region}"
        )
        spec = None
        for key in ("specialization", "active_spec"):
            value = data.get(key)
            if isinstance(value, dict):
                spec = value.get("name")
                break
        rating = None
        avatar_url = None
        render_url = None
        try:
            mplus = await self._get(
                region, f"/profile/wow/character/{realm}/{character}/mythic-keystone-profile",
                namespace=f"profile-{region}",
            )
            raw_rating = (mplus.get("current_mythic_rating") or {}).get("rating")
            if raw_rating is not None:
                rating = int(round(raw_rating))
        except (BlizzardError, httpx.HTTPError, TypeError, ValueError):
            rating = None
        try:
            media = await self._get(
                region, f"/profile/wow/character/{realm}/{character}/character-media",
                namespace=f"profile-{region}",
            )
            assets = media.get("assets") or []
            avatar_url = next((a.get("value") for a in assets if a.get("key") == "avatar"), None)
            render_url = next((a.get("value") for a in assets if a.get("key") == "main-raw"), None)
        except (BlizzardError, httpx.HTTPError):
            avatar_url = render_url = None
        return CharacterSummary(
            name=data.get("name") or character,
            realm=(data.get("realm") or {}).get("slug") or realm,
            region=region,
            faction=(data.get("faction") or {}).get("name"),
            race=(data.get("race") or {}).get("name"),
            class_name=(data.get("character_class") or {}).get("name"),
            spec=spec,
            level=data.get("level"),
            average_item_level=data.get("average_item_level"),
            achievement_points=data.get("achievement_points"),
            mythic_plus_rating=rating,
            avatar_url=avatar_url,
            render_url=render_url,
        )

    async def equipment(self, region: str, realm: str, character: str) -> dict[str, EquippedItem]:
        data = await self._get(
            region, f"/profile/wow/character/{realm}/{character}/equipment",
            namespace=f"profile-{region}",
        )
        equipped: dict[str, EquippedItem] = {}
        for item in data.get("equipped_items", []):
            slot_type = (item.get("slot") or {}).get("type", "")
            slot = SLOT_MAP.get(slot_type)
            if not slot:
                continue
            enchant = None
            enchantments = item.get("enchantments") or []
            if enchantments:
                enchant = enchantments[0].get("display_string")
            details = item.get("item") or {}
            equipped[slot] = EquippedItem(
                slot=slot,
                item_id=details.get("id", 0),
                name=item.get("name") or details.get("name", "Unknown"),
                ilvl=(item.get("level") or {}).get("value", 0),
                quality=(item.get("quality") or {}).get("name"),
                enchant=enchant,
                inventory_type=(item.get("inventory_type") or {}).get("type"),
            )

        async with self._make_client() as client:
            icon_urls = await self._item_icons(
                client, region, [entry.item_id for entry in equipped.values()]
            )
        for slot, entry in equipped.items():
            entry.icon_url = icon_urls.get(entry.item_id)
        return equipped

    async def _item_icons(
        self, client: httpx.AsyncClient, region: str, item_ids: list[int]
    ) -> dict[int, str | None]:
        """Icon URL per item id, using a global cache and batched requests."""
        results: dict[int, str | None] = {}
        missing: list[int] = []
        for item_id in item_ids:
            cached = _ITEM_MEDIA_CACHE.get((region, item_id))
            if cached is not None:
                results[item_id] = cached
            else:
                missing.append(item_id)

        async def fetch(item_id: int) -> None:
            icon_url = None
            try:
                media = await self._request(
                    client, region, f"/data/wow/media/item/{item_id}", namespace=f"static-{region}"
                )
                assets = media.get("assets") or []
                icon_url = next((a.get("value") for a in assets if a.get("key") == "icon"), None)
            except (BlizzardError, httpx.HTTPError):
                icon_url = None
            if icon_url:
                _ITEM_MEDIA_CACHE[(region, item_id)] = icon_url
                self._persist_icon_cache()
            results[item_id] = icon_url

        for i in range(0, len(missing), 4):  # keep concurrency modest (burst protection)
            await asyncio.gather(*(fetch(item_id) for item_id in missing[i:i + 4]))
            await asyncio.sleep(0.3)
        return results

    def _persist_icon_cache(self) -> None:
        try:
            payload = {f"{region}:{item_id}": url for (region, item_id), url in _ITEM_MEDIA_CACHE.items()}
            _ICON_CACHE_PATH.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass
