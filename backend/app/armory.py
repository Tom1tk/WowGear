"""Armory HTML scraper — keyless fallback data source.

The retail Armory page embeds a full character state JSON blob
(`characterProfileInitialState`), which mirrors the Blizzard Profile API shape:
identity, spec, item level and all 16 equipped gear slots. Used when the
official API is unavailable (no key / key not provisioned / API moved).
"""

import json
import re

import httpx

from .models import CharacterSummary, EquippedItem

ARMORY_BASE = "https://worldofwarcraft.blizzard.com"

REGION_LOCALE_PATH = {
    "eu": "en-gb",
    "us": "en-us",
    "kr": "ko-kr",
    "tw": "zh-tw",
}

# armory gear keys -> normalized slot names
GEAR_KEY_TO_SLOT = {
    "head": "head",
    "neck": "neck",
    "shoulder": "shoulders",
    "back": "back",
    "chest": "chest",
    "wrist": "wrist",
    "hand": "hands",
    "waist": "waist",
    "leg": "legs",
    "foot": "feet",
    "leftFinger": "ring_1",
    "rightFinger": "ring_2",
    "leftTrinket": "trinket_1",
    "rightTrinket": "trinket_2",
    "weapon": "main_hand",
    "offhand": "off_hand",
}

STATE_PATTERN = re.compile(
    r"characterProfileInitialState\s*=\s*(\{.*?\})\s*;\s*</script>", re.DOTALL
)


class ArmoryError(Exception):
    pass


class ArmoryCharacterNotFoundError(ArmoryError):
    pass


class ArmoryParseError(ArmoryError):
    pass


def parse_armory_page(html: str, region: str) -> tuple[CharacterSummary, dict[str, EquippedItem]]:
    """Parse the embedded character state out of an Armory HTML page."""
    match = STATE_PATTERN.search(html)
    if not match:
        raise ArmoryParseError(
            "Could not find character data in the Armory page (site structure may have changed)."
        )
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ArmoryParseError(f"Malformed character data in Armory page: {exc}") from exc

    character = payload.get("character") or payload.get("summary") or {}
    gear_raw = character.get("gear") or {}

    equipped: dict[str, EquippedItem] = {}
    for key, slot in GEAR_KEY_TO_SLOT.items():
        entry = gear_raw.get(key)
        if not entry:
            continue
        equipped[slot] = EquippedItem(
            slot=slot,
            item_id=entry.get("id", 0),
            name=entry.get("name", "Unknown"),
            ilvl=(entry.get("level") or {}).get("value", 0),
            quality=(entry.get("quality") or {}).get("name"),
        )

    spec = character.get("spec")
    avatar = character.get("avatar")
    if isinstance(avatar, dict):
        avatar = avatar.get("url")
    render_raw = character.get("renderRaw")
    if isinstance(render_raw, dict):
        render_raw = render_raw.get("url")
    summary = CharacterSummary(
        name=character.get("name") or "?",
        realm=(character.get("realm") or {}).get("slug") or "?",
        region=region,
        faction=(character.get("faction") or {}).get("name"),
        race=(character.get("race") or {}).get("name"),
        class_name=(character.get("class") or {}).get("name"),
        spec=spec.get("name") if isinstance(spec, dict) else None,
        level=character.get("level"),
        average_item_level=character.get("averageItemLevel"),
        achievement_points=character.get("achievement"),
        mythic_plus_rating=(character.get("dungeonRating") or {}).get("rating"),
        avatar_url=avatar,
        render_url=render_raw,
    )
    return summary, equipped


async def fetch_armory_page(region: str, realm: str, character: str) -> str:
    locale_path = REGION_LOCALE_PATH.get(region, "en-us")
    url = f"{ARMORY_BASE}/{locale_path}/character/{region}/{realm}/{character}"
    async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
        resp = await client.get(url)
    if resp.status_code == 404:
        raise ArmoryCharacterNotFoundError(
            f"Character not found on the Armory: {region}/{realm}/{character}"
        )
    if resp.status_code != 200:
        raise ArmoryError(f"Armory request failed with HTTP {resp.status_code}.")
    return resp.text
