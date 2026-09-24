"""Fetch human-made pre-raid BiS lists as a reference for validation.

Source: wowtbc.gg Classic pre-raid lists (robots.txt allows crawling). The
lists are only used to CHECK our computed lists (scripts/data/validate.py);
they are not shown on the site. Only item names and slots are stored.

    python scripts/data/fetch_reference.py
"""

from __future__ import annotations

import os
import re
import sys
import time

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(__file__))
from _common import ERA, RAW, write_json  # noqa: E402

BASE = "https://wowtbc.gg/classic/bis-list/{}/"
SPECS = {
    "druid.feral_cat": "feral-dps-druid", "druid.feral_bear": "feral-tank-druid",
    "druid.balance": "balance-druid", "druid.restoration": "restoration-druid",
    "shaman.enhancement": "enhancement-shaman", "shaman.elemental": "elemental-shaman",
    "shaman.restoration": "restoration-shaman",
    "warrior.arms": "arms-warrior", "warrior.fury": "fury-warrior", "warrior.protection": "protection-warrior",
    "paladin.holy": "holy-paladin", "paladin.protection": "protection-paladin", "paladin.retribution": "retribution-paladin",
    "hunter.beast_mastery": "beast-mastery-hunter", "hunter.marksmanship": "marksmanship-hunter",
    "hunter.survival": "survival-hunter",
    "rogue.combat": "combat-rogue", "rogue.assassination": "assassination-rogue", "rogue.subtlety": "subtlety-rogue",
    "priest.holy": "holy-priest", "priest.discipline": "discipline-priest", "priest.shadow": "shadow-priest",
    "mage.fire": "fire-mage", "mage.frost": "frost-mage", "mage.arcane": "arcane-mage",
    "warlock.affliction": "affliction-warlock", "warlock.destruction": "destruction-warlock",
    "warlock.demonology": "demonology-warlock",
}
_UNUSED_SLOT_RE = re.compile(r"^(head|neck|shoulder|back|chest|wrist|hands|waist|legs|feet|finger \d|trinket \d|"
                     r"main hand|off hand|two hand|ranged|relic|wand|idol|totem|libram|weapon|"
                     r"[a-z]+ weapon|[a-z]+ main hand|[a-z]+ off hand|[a-z]+ two hand|[a-z]+ ranged)$")


def parse(html: str) -> list[dict]:
    """Each slot is a div.bis__card (id = slot); the first div.item__name in it
    is the recommended item."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for card in soup.select("div.bis__card"):
        name = card.select_one("div.item__name")
        slot = card.get("id") or ""
        if name and slot:
            out.append({"slot": slot.replace("-", " "), "item": name.get_text(strip=True)})
    return out


def main():
    cache = RAW / "reference"
    cache.mkdir(parents=True, exist_ok=True)
    result = {"_about": "Pre-raid BiS lists from wowtbc.gg (Classic), for validation only.", "lists": {}}
    with httpx.Client(timeout=30, follow_redirects=True,
                      headers={"User-Agent": "WowGearBis data check (hobby project)"}) as client:
        for key, slug in SPECS.items():
            path = cache / f"wowtbc_{slug}.html"
            if not path.exists():
                resp = client.get(BASE.format(slug))
                if resp.status_code != 200:
                    print(f"{key}: HTTP {resp.status_code}")
                    continue
                path.write_text(resp.text, encoding="utf-8")
                time.sleep(1.0)
            rows = parse(path.read_text(encoding="utf-8"))
            result["lists"][key] = {"url": BASE.format(slug), "items": rows}
            print(f"{key}: {len(rows)} items")
    write_json(ERA / "reference" / "wowtbc_preraid.json", result)


if __name__ == "__main__":
    main()
