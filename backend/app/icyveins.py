"""Icy Veins Best-in-Slot page parser and fetcher."""

import json
import re
import time

import httpx
from bs4 import BeautifulSoup

from .models import BisItem, FarmTip

BASE_URL = "https://www.icy-veins.com/wow/"

SLOT_ALIASES = {
    "Helm": "head", "Head": "head", "Neck": "neck", "Shoulders": "shoulders",
    "Cloak": "back", "Chest": "chest", "Bracers": "wrist", "Hands": "hands",
    "Waist": "waist", "Legs": "legs", "Feet": "feet",
    "Main Hand": "main_hand", "Off Hand": "off_hand",
}

POSITIONAL_SLOTS = {"Ring": "ring", "Trinket": "trinket"}

BONUS_TRACKS = {
    13786: "Mythic Raid",
    12806: "Mythic+",
    13654: "Heroic Raid",
    13124: "Heroic Raid",
}

FAVORITE_QUESTIONS = ("Dungeons Should I Farm", "Raid Drops Are Most Important")


class IcyVeinsError(Exception):
    pass


class PageNotFoundError(IcyVeinsError):
    pass


class ParseError(IcyVeinsError):
    pass


def parse_bis_page(html: str) -> tuple[list[BisItem], int, list[FarmTip]]:
    """Parse an Icy Veins BiS page into items, max item level and farm tips.

    Uses the "Overall Best in Slot" grid (id bis_0_0). Ring/Trinket slots are
    positional: the second occurrence maps to ring_2 / trinket_2.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[BisItem] = []
    positions = {"ring": 0, "trinket": 0}

    grid = soup.find(id="bis_0_0") or soup
    for element in grid.select("div.bis_item"):
        slot_el = element.select_one("span.bis_item_slot")
        name_el = element.select_one("span[data-wowhead^='item='][class^='q']")
        if not slot_el or not name_el:
            continue
        raw_slot = slot_el.get_text(strip=True)
        if raw_slot in SLOT_ALIASES:
            slot = SLOT_ALIASES[raw_slot]
        elif raw_slot in POSITIONAL_SLOTS:
            positions[POSITIONAL_SLOTS[raw_slot]] += 1
            slot = f"{POSITIONAL_SLOTS[raw_slot]}_{positions[POSITIONAL_SLOTS[raw_slot]]}"
        else:
            continue

        match = re.match(r"item=(\d+)(?:&(?:amp;)?bonus=([^;]*))?", name_el["data-wowhead"])
        if not match:
            continue
        item_id = int(match.group(1))
        # Bonus strings can contain empty segments (e.g. "1111::2222"); only
        # keep segments that actually parse as integers.
        bonus = []
        if match.group(2):
            for segment in match.group(2).split(":"):
                if segment.isdigit():
                    bonus.append(int(segment))
        track = None
        for bonus_id in bonus:
            if bonus_id in BONUS_TRACKS:
                track = BONUS_TRACKS[bonus_id]
                break

        drop_el = element.select_one("span.bis_item_drop")
        drop = drop_el.get_text(" ", strip=True) if drop_el else ""
        drop_links = [a.get("href", "") for a in drop_el.select("a")] if drop_el else []
        drop_link_texts = [
            a.get_text(" ", strip=True) for a in drop_el.select("a")
        ] if drop_el else []

        enchant_el = element.select_one("span.bis_item_enchant")
        enchant = enchant_el.get_text(" ", strip=True) if enchant_el else None

        extras_el = element.select_one("div.bis_item_extras")
        gems = []
        if extras_el:
            gems = [g.get_text(" ", strip=True) for g in extras_el.select("span[class^='q']")]

        items.append(
            BisItem(
                slot=slot,
                item_id=item_id,
                name=name_el.get_text(strip=True),
                ilvl=0,
                track=track,
                drop=drop,
                drop_links=drop_links,
                drop_link_texts=drop_link_texts,
                enchant=enchant,
                gems=gems,
            )
        )

    if not items:
        raise ParseError(
            "No BiS items found on the Icy Veins page (site structure may have changed)."
        )
    return items, _extract_max_ilvl(soup), _extract_farm_tips(soup)


def _extract_max_ilvl(soup: BeautifulSoup) -> int:
    match = re.search(r"highest possible item level of (\d+)", soup.get_text(" ", strip=True))
    return int(match.group(1)) if match else 0


def _extract_farm_tips(soup: BeautifulSoup) -> list[FarmTip]:
    tips: list[FarmTip] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        nodes = data.get("@graph") or [data]
        for node in nodes:
            if node.get("@type") != "FAQPage":
                continue
            for question in node.get("mainEntity", []):
                name = question.get("name", "")
                if any(needle in name for needle in FAVORITE_QUESTIONS):
                    tips.append(
                        FarmTip(
                            title=name,
                            text=question.get("acceptedAnswer", {}).get("text", ""),
                        )
                    )
    return tips


class BisPageFetcher:
    """Fetches and caches Icy Veins BiS pages (in-memory TTL cache)."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self.ttl = ttl_seconds
        self._cache: dict[str, tuple[float, str]] = {}

    async def fetch(self, slug: str) -> str:
        now = time.time()
        cached = self._cache.get(slug)
        if cached and now - cached[0] < self.ttl:
            return cached[1]
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            resp = await client.get(BASE_URL + slug)
        if resp.status_code == 404:
            raise PageNotFoundError(f"Icy Veins page not found: {slug}")
        if resp.status_code != 200:
            raise IcyVeinsError(
                f"Icy Veins request failed with HTTP {resp.status_code}."
            )
        self._cache[slug] = (now, resp.text)
        return resp.text
