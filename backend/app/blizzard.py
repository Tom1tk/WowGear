"""Blizzard Profile API client for WoW Forever.

Forever has no realms. Namespaces are profile-forever-{region},
static-forever-{region} and dynamic-forever-{region} (community-verified, not
documented by Blizzard). A character is addressed by first name + surname.
"""

import asyncio
import base64
import time
from urllib.parse import quote

import httpx

from .models import CharacterSummary, EquippedItem, TalentTree, WornItem, WornWeapon

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
    return f"{kind}-forever-{region}"


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
                "Character not found. Forever characters show up from level 10, "
                "after logging out. Check first name, surname and region."
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

    async def character(self, region: str, name: str, surname: str) -> tuple[
            CharacterSummary, dict[str, EquippedItem], list[TalentTree]]:
        base = "/profile/wow/character/" + quote(f"{name}-{surname}".lower())
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
            surname=profile.get("surname") or surname,
            region=region,
            level=profile.get("level") or 0,
            faction=((profile.get("faction") or {}).get("type") or "")[:1] or None,
            race=(profile.get("race") or {}).get("name"),
            race_id=(profile.get("race") or {}).get("id"),
            class_name=(profile.get("character_class") or {}).get("name"),
            class_id=(profile.get("character_class") or {}).get("id"),
            guild=(profile.get("guild") or {}).get("name"),
            avatar_url=next((a.get("value") for a in assets if a.get("key") == "avatar"), None),
            ruleset=parse_ruleset(profile.get("ruleset")),
        )
        return summary, parse_equipment(equipment), parse_talents(talents)


def parse_ruleset(value) -> str | None:
    """Shape unknown: a plain string, or an object with a name."""
    if isinstance(value, dict):
        value = value.get("name")
    return value if isinstance(value, str) and value else None


# Blizzard stat types -> our stat keys (same as scripts/data/parse_blizzard.py); others are lowercased,
# which matches the rating keys the scorer knows (e.g. CRIT_RATING -> crit_rating).
STAT_KEYS = {
    "STRENGTH": "str", "AGILITY": "agi", "STAMINA": "sta", "INTELLECT": "int", "SPIRIT": "spi",
    "ATTACK_POWER": "ap", "SPELL_POWER": "sp", "EXTRA_ARMOR": "bonus_armor",
    "FIRE_RESISTANCE": "res_fire", "NATURE_RESISTANCE": "res_nature", "FROST_RESISTANCE": "res_frost",
    "SHADOW_RESISTANCE": "res_shadow", "ARCANE_RESISTANCE": "res_arcane",
}


def parse_worn(entry: dict) -> WornItem | None:
    """Stats of one equipped item as the API shows them, or None when the entry has no item class."""
    cls, sub = entry.get("item_class") or {}, entry.get("item_subclass") or {}
    if "id" not in cls or "id" not in sub:
        return None
    stats: dict[str, float] = {}
    for s in entry.get("stats") or []:
        stype = (s.get("type") or {}).get("type")
        if stype and not s.get("is_negated") and isinstance(s.get("value"), (int, float)):
            key = STAT_KEYS.get(stype, stype.lower())
            stats[key] = stats.get(key, 0) + s["value"]
    if (entry.get("armor") or {}).get("value"):
        stats["armor"] = entry["armor"]["value"]
    if (entry.get("shield_block") or {}).get("value"):
        stats["block_value"] = stats.get("block_value", 0) + entry["shield_block"]["value"]
    w = entry.get("weapon") or {}
    weapon = None
    if (w.get("dps") or {}).get("value") and (w.get("attack_speed") or {}).get("value"):
        weapon = WornWeapon(dps=round(w["dps"]["value"], 2), speed=round(w["attack_speed"]["value"] / 1000, 2))
    return WornItem(name=entry.get("name") or "", item_class=cls["id"], subclass=sub["id"],
                    inventory_type=(entry.get("inventory_type") or {}).get("type") or "", stats=stats, weapon=weapon)


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
            worn=parse_worn(entry),
        )
    return equipped


def parse_talents(data: dict) -> list[TalentTree]:
    groups = data.get("specialization_groups") or []
    if groups:  # Era shape
        active = next((g for g in groups if g.get("is_active")), groups[0])
        specs = active.get("specializations") or []
    else:  # retail-like shape; unknown shapes give []
        specs = data.get("specializations") or []
    trees = [
        TalentTree(
            name=s.get("specialization_name") or (s.get("specialization") or {}).get("name") or "",
            points=s.get("spent_points") or len(s.get("talents") or []),
        )
        for s in specs if isinstance(s, dict)
    ]
    if not trees and isinstance(data.get("active_specialization"), dict):
        name = data["active_specialization"].get("name")
        if name:
            trees = [TalentTree(name=name, points=1)]
    return trees
