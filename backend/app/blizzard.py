"""Blizzard Game Data / Profile API client for WoW Classic Era.

Era realms use the `classic1x` namespaces (profile-classic1x-{region},
dynamic-classic1x-{region}, static-classic1x-{region}).
"""

import asyncio
import base64
import time

import httpx

from .models import CharacterSummary, EquippedItem, TalentTree

TOKEN_URL = "https://oauth.battle.net/token"

SLOT_MAP = {
    "HEAD": "head", "NECK": "neck", "SHOULDER": "shoulders", "BACK": "back",
    "CHEST": "chest", "WRIST": "wrist", "HANDS": "hands", "WAIST": "waist",
    "LEGS": "legs", "FEET": "feet", "FINGER_1": "ring_1", "FINGER_2": "ring_2",
    "TRINKET_1": "trinket_1", "TRINKET_2": "trinket_2", "MAIN_HAND": "main_hand",
    "OFF_HAND": "off_hand", "RANGED": "ranged",
}


class BlizzardError(Exception):
    """Base error for Blizzard API failures."""


class ApiKeyMissingError(BlizzardError):
    """No client id/secret configured."""


class ApiKeyInvalidError(BlizzardError):
    """Blizzard rejected the credentials."""


class CharacterNotFoundError(BlizzardError):
    """The character does not exist (or its profile is private)."""


class RateLimitedError(BlizzardError):
    """Too many requests."""


def namespace(kind: str, region: str) -> str:
    return f"{kind}-classic1x-{region}"


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
        # Tokens are not cached on purpose: Blizzard starts rejecting a token
        # after heavy reuse, and a fresh one per request batch is reliable.
        auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        resp = await client.post(
            TOKEN_URL, headers={"Authorization": f"Basic {auth}"},
            data={"grant_type": "client_credentials"},
        )
        if resp.status_code == 401:
            raise ApiKeyInvalidError(
                "Blizzard rejected the API credentials (401). "
                "Check BLIZZARD_CLIENT_ID / BLIZZARD_CLIENT_SECRET."
            )
        if resp.status_code != 200:
            raise BlizzardError(f"Blizzard token request failed (HTTP {resp.status_code}).")
        return resp.json()["access_token"]

    async def _request(self, client: httpx.AsyncClient, region: str, path: str, ns: str) -> dict:
        if not (self.client_id and self.client_secret):
            raise ApiKeyMissingError(
                "The Blizzard API key is not set up on this server. "
                "Use 'Enter manually' to plan your gear without it."
            )
        token = await self._get_token(client)
        url = f"https://{region}.api.blizzard.com{path}"
        params = {"namespace": ns, "locale": "en_US"}
        headers = {"Authorization": f"Bearer {token}"}
        for attempt in range(3):
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 429 and attempt < 2:
                await asyncio.sleep(0.6 * (attempt + 1))
                continue
            break
        if resp.status_code == 404:
            raise CharacterNotFoundError(
                "Character not found on this Classic Era realm. Check the name and realm, "
                "and log in once in game if the character is new."
            )
        if resp.status_code == 401:
            raise ApiKeyInvalidError("Blizzard rejected the API key (401).")
        if resp.status_code == 429:
            raise RateLimitedError("The Blizzard API is busy (rate limit). Try again in a moment.")
        if resp.status_code != 200:
            raise BlizzardError(f"Blizzard API request failed (HTTP {resp.status_code}).")
        return resp.json()

    async def _get(self, region: str, path: str, ns: str) -> dict:
        key = (region, path, ns)
        cached = self._response_cache.get(key)
        if cached and time.time() - cached[0] < self._cache_ttl:
            return cached[1]
        async with self._make_client() as client:
            data = await self._request(client, region, path, ns)
        self._response_cache[key] = (time.time(), data)
        return data

    async def realms(self, region: str) -> list[dict]:
        data = await self._get(region, "/data/wow/realm/index", namespace("dynamic", region))
        realms = [
            {"slug": r["slug"], "name": r["name"]}
            for r in data.get("realms", [])
            if r.get("slug") and not _is_internal_realm(r.get("name", ""))
        ]
        return sorted(realms, key=lambda r: r["name"].lower())

    async def character(self, region: str, realm: str, name: str) -> tuple[
            CharacterSummary, dict[str, EquippedItem], list[TalentTree]]:
        base = f"/profile/wow/character/{realm}/{name}"
        ns = namespace("profile", region)
        profile = await self._get(region, base, ns)

        async def optional(path: str) -> dict:
            try:
                return await self._get(region, base + path, ns)
            except (BlizzardError, httpx.HTTPError):
                return {}

        equipment, talents, media = await asyncio.gather(
            optional("/equipment"), optional("/specializations"), optional("/character-media"),
        )
        assets = media.get("assets") or []
        summary = CharacterSummary(
            name=profile.get("name") or name,
            realm=(profile.get("realm") or {}).get("name") or realm,
            region=region,
            level=profile.get("level") or 0,
            faction=((profile.get("faction") or {}).get("type") or "")[:1] or None,
            race=(profile.get("race") or {}).get("name"),
            race_id=(profile.get("race") or {}).get("id"),
            class_name=(profile.get("character_class") or {}).get("name"),
            class_id=(profile.get("character_class") or {}).get("id"),
            guild=(profile.get("guild") or {}).get("name"),
            avatar_url=next((a.get("value") for a in assets if a.get("key") == "avatar"), None),
        )
        return summary, parse_equipment(equipment), parse_talents(talents)


def _is_internal_realm(name: str) -> bool:
    """Blizzard lists a few internal test realms (e.g. 'EU4 CWOW GMSS 1')."""
    upper = name.upper()
    return "CWOW" in upper or "GMSS" in upper


def parse_equipment(data: dict) -> dict[str, EquippedItem]:
    equipped: dict[str, EquippedItem] = {}
    for entry in data.get("equipped_items", []):
        slot = SLOT_MAP.get((entry.get("slot") or {}).get("type", ""))
        if not slot:
            continue
        inv = (entry.get("inventory_type") or {}).get("type")
        if slot == "main_hand" and inv == "TWOHWEAPON":
            slot = "two_hand"
        enchants = entry.get("enchantments") or []
        equipped[slot] = EquippedItem(
            slot=slot,
            item_id=(entry.get("item") or {}).get("id", 0),
            name=entry.get("name") or "Unknown item",
            quality=(entry.get("quality") or {}).get("type"),
            inventory_type=inv,
            enchant=enchants[0].get("display_string") if enchants else None,
        )
    return equipped


def parse_talents(data: dict) -> list[TalentTree]:
    groups = data.get("specialization_groups") or []
    active = next((g for g in groups if g.get("is_active")), groups[0] if groups else None)
    if not active:
        return []
    return [
        TalentTree(name=s.get("specialization_name") or "", points=s.get("spent_points") or 0)
        for s in active.get("specializations", [])
    ]
