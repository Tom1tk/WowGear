"""Class rules, spec detection and item scoring (uses the committed data)."""

from app.models import TalentTree
from app.scoring import scorer
from app.specs import detect_spec

WARRIOR, PALADIN, HUNTER, ROGUE, PRIEST, SHAMAN, MAGE, WARLOCK, DRUID = "1", "2", "3", "4", "5", "7", "8", "9", "11"


def item(**kw):
    base = {"class": 4, "subclass": 1, "inventory_type": "CHEST", "stats": {}, "quality": 2}
    base.update(kw)
    return base


def test_plate_and_mail_from_level_40():
    plate = item(subclass=4)
    mail = item(subclass=3)
    assert scorer.usable_from(plate, WARRIOR) == 40
    assert scorer.usable_from(plate, PALADIN) == 40
    assert scorer.usable_from(mail, WARRIOR) == 1
    assert scorer.usable_from(mail, SHAMAN) == 40
    assert scorer.usable_from(mail, HUNTER) == 40
    assert scorer.usable_from(mail, DRUID) is None
    assert scorer.usable_from(plate, ROGUE) is None


def test_weapon_rules():
    sword = item(**{"class": 2, "subclass": 7, "inventory_type": "WEAPON"})
    offhand_axe = item(**{"class": 2, "subclass": 0, "inventory_type": "WEAPONOFFHAND"})
    assert scorer.usable_from(sword, DRUID) is None       # druids cannot use swords
    assert scorer.usable_from(sword, ROGUE) == 1
    assert scorer.usable_from(offhand_axe, WARRIOR) == 1
    wand = item(**{"class": 2, "subclass": 19, "inventory_type": "RANGEDRIGHT"})
    assert scorer.usable_from(wand, MAGE) == 1 and scorer.usable_from(wand, WARRIOR) is None


def test_relics_are_class_specific():
    idol = item(subclass=8, inventory_type="RELIC")
    totem = item(subclass=9, inventory_type="RELIC")
    assert scorer.usable_from(idol, DRUID) == 1
    assert scorer.usable_from(idol, SHAMAN) is None
    assert scorer.usable_from(totem, SHAMAN) == 1


def test_min_level_floor_for_items_without_requirement():
    assert scorer.min_level({"required_level": 0, "item_level": 55}) == 50
    assert scorer.min_level({"required_level": 24, "item_level": 29}) == 24


def test_class_limited_effect_is_ignored_for_other_classes(monkeypatch):
    monkeypatch.setitem(scorer.effects, "900001", {"name": "Invented Charm", "stats": {"ap": 20}, "classes": [11]})
    charm = {"class": 4, "subclass": 0, "inventory_type": "TRINKET", "stats": {"ap": 20}, "quality": 3}
    assert scorer.score(charm, "900001", {"ap": 1}, {}, "trinket", None, ROGUE) == 20  # item stat only
    assert scorer.score(charm, "900001", {"ap": 1}, {}, "trinket", None, DRUID) == 20  # raw mode: effects not counted
    assert scorer.score(charm, "900001", {"ap": 1}, {}, "trinket", None, ROGUE, bonus=True) == 20
    assert scorer.score(charm, "900001", {"ap": 1}, {}, "trinket", None, DRUID, bonus=True) == 40  # stat + effect


def test_unified_hit_and_crit_rating_aliases():
    ring = {"class": 4, "subclass": 0, "inventory_type": "FINGER", "stats": {"hit_rating": 10, "spell_crit": 5}}
    assert scorer.score(ring, "900002", {"hit": 2, "crit": 3}, {}, "ring", None, ROGUE) == 17  # 10 hit rating = 1% hit


def test_crit_rating_scores_as_percent():
    gloves = {"class": 4, "subclass": 2, "inventory_type": "HAND", "stats": {"crit_rating": 14, "parry_rating": -15}}
    assert scorer.score(gloves, "900004", {"crit": 20, "parry": 5}, {}, "hands", None, DRUID) == 15  # +1% crit, -1% parry


def test_strength_scores_for_enhancement_not_for_mage(monkeypatch):
    axe = {"class": 2, "subclass": 1, "inventory_type": "TWOHWEAPON", "stats": {"str": 30},
           "weapon": {"dps": 60, "speed": 3.5}, "required_level": 60, "item_level": 70, "quality": 4}
    monkeypatch.setitem(scorer.items, "900003", axe)
    assert scorer.score_for("900003", SHAMAN, "enhancement", 60) > 50
    assert scorer.score_for("900003", MAGE, "frost", 60) is None  # mages cannot use axes


def test_detect_spec_from_talent_points():
    trees = [TalentTree(name="Fury", points=34), TalentTree(name="Arms", points=17), TalentTree(name="Protection", points=0)]
    assert detect_spec(1, 60, trees)[0] == "fury"
    feral = [TalentTree(name="Balance", points=0), TalentTree(name="Feral Combat", points=20),
             TalentTree(name="Restoration", points=5)]
    spec, reason = detect_spec(11, 30, feral)
    assert spec == "feral_cat" and "Bear" in reason


def test_detect_spec_without_talents_uses_leveling_spec():
    spec, reason = detect_spec(7, 8, [])
    assert spec == "enhancement" and "level 10" in reason
