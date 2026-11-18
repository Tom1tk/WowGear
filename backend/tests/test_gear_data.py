"""Sanity checks on the generated gear files (frontend/data/gear)."""

import json
from pathlib import Path

import pytest

from app.scoring import scorer

GEAR = Path(__file__).resolve().parents[2] / "frontend" / "data" / "gear"
META = json.loads((GEAR.parent / "meta.json").read_text())


def gear_files():
    return sorted(GEAR.glob("*.json"))


def test_every_class_spec_faction_has_a_file():
    names = {p.name for p in gear_files()}
    for cid, cls in scorer.classes.items():
        factions = {r["faction"] for r in scorer.races.values() if int(cid) in r["classes"]}
        for spec in cls["specs"]:
            for fac in factions:
                assert f"{cls['slug']}.{spec}.{fac}.json" in names


@pytest.mark.parametrize("path", gear_files()[:: max(1, len(gear_files()) // 12)], ids=lambda p: p.stem)
def test_items_respect_level_and_class(path):
    data = json.loads(path.read_text())
    cls_id = str(data["class_id"])
    for slot, points in data["slots"].items():
        for point in points:
            for iid, *_score in point["items"]:
                it = scorer.items[iid]
                assert scorer.min_level(it) <= point["level"], (slot, it["name"], point["level"])
                usable = scorer.usable_from(it, cls_id)
                assert usable is not None and usable <= point["level"], (slot, it["name"])


def test_pre_raid_lists_have_no_raid_sources():
    data = json.loads((GEAR / "druid.feral_cat.A.json").read_text())
    raids = {k for k, v in META["instances"].items() if v["tier"]}
    for slot, points in data["slots"].items():
        for point in points:
            if point["tier"]:
                continue
            for iid, *_ in point["items"]:
                srcs = data["items"][iid]["sources"]
                assert srcs and not all(s.get("instance") in raids for s in srcs), data["items"][iid]["name"]


def test_items_carry_checks_and_conflict_reasons():
    for path in gear_files()[:: max(1, len(gear_files()) // 6)]:
        for it in json.loads(path.read_text())["items"].values():
            assert "uncertain" in it and "checks" in it
            for src in it["sources"]:
                assert "conflict" in src and (not src["conflict"] or src.get("conflict_reason"))


def test_meta_has_skyborne_and_raid_tier():
    assert META["game"] == "forever"
    assert META["races"]["95"]["classes"] and META["races"]["96"]["faction"] == "H"
    assert "1" in META["tiers"] and "1" in META["tier_notes"]
