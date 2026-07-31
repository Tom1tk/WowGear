"""Blizzard Game Data API client (OAuth2 client credentials flow)."""

import base64
import time

import httpx

from .models import CharacterSummary, EquippedItem

TOKEN_URL = "https://oauth.battle.net/token"

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
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._timeout = timeout
        self._transport = transport
        self._token: str | None = None
        self._token_expires_at = 0.0

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._timeout, transport=self._transport)

    async def _get_token(self, client: httpx.AsyncClient) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
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
        self._token = payload["access_token"]
        self._token_expires_at = time.time() + payload.get("expires_in", 86400)
        return self._token

    async def _get(self, region: str, path: str) -> dict:
        if not (self.client_id and self.client_secret):
            raise ApiKeyMissingError(
                "Blizzard API key is not configured. "
                "Register at https://develop.battle.net and add "
                "BLIZZARD_CLIENT_ID / BLIZZARD_CLIENT_SECRET to .env, then restart."
            )
        async with self._make_client() as client:
            token = await self._get_token(client)
            resp = await client.get(
                f"https://{region}.api.blizzard.com{path}",
                params={
                    "namespace": f"profile-{region}",
                    "locale": "en_US",
                },
                headers={"Authorization": f"Bearer {token}"},
            )
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
        if resp.status_code == 429:
            raise RateLimitedError("Blizzard API rate limit reached (429). Try again shortly.")
        if resp.status_code != 200:
            raise BlizzardError(
                f"Blizzard API request failed with HTTP {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json()

    async def character_summary(self, region: str, realm: str, character: str) -> CharacterSummary:
        data = await self._get(region, f"/profile/wow/character/{realm}/{character}")
        spec = None
        for key in ("specialization", "active_spec"):
            value = data.get(key)
            if isinstance(value, dict):
                spec = value.get("name")
                break
        rating = None
        try:
            mplus = await self._get(
                region, f"/profile/wow/character/{realm}/{character}/mythic-keystone-profile"
            )
            raw_rating = mplus.get("current_mythic_rating", {}).get("rating")
            if raw_rating is not None:
                rating = int(round(raw_rating))
        except (BlizzardError, httpx.HTTPError, TypeError, ValueError):
            rating = None
        return CharacterSummary(
            name=data.get("name") or character,
            realm=data.get("realm", {}).get("slug") or realm,
            region=region,
            faction=data.get("faction", {}).get("name"),
            race=data.get("race", {}).get("name"),
            class_name=data.get("character_class", {}).get("name"),
            spec=spec,
            level=data.get("level"),
            average_item_level=data.get("average_item_level"),
            achievement_points=data.get("achievement_points"),
            mythic_plus_rating=rating,
        )

    async def equipment(self, region: str, realm: str, character: str) -> dict[str, EquippedItem]:
        data = await self._get(
            region, f"/profile/wow/character/{realm}/{character}/equipment"
        )
        equipped: dict[str, EquippedItem] = {}
        for item in data.get("equipped_items", []):
            slot_type = item.get("slot", {}).get("type", "")
            slot = SLOT_MAP.get(slot_type)
            if not slot:
                continue
            enchant = None
            enchantments = item.get("enchantments") or []
            if enchantments:
                enchant = enchantments[0].get("display_string")
            details = item.get("item", {})
            equipped[slot] = EquippedItem(
                slot=slot,
                item_id=details.get("id", 0),
                name=item.get("name") or details.get("name", "Unknown"),
                ilvl=item.get("level", {}).get("value", 0),
                quality=item.get("quality", {}).get("name"),
                enchant=enchant,
            )
        return equipped
