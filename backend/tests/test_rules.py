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
    assert scorer.usable_from(offhand_axe, SHAMAN) is None  # no dual wield in Classic
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


def test_hand_kept_effect_is_added_to_the_score():
    wolfshead = scorer.items["8345"]
    assert wolfshead["name"] == "Wolfshead Helm"
    assert scorer.score_for("8345", DRUID, "feral_cat", 60) >= 70  # effect value, not only Spirit
    assert scorer.score_for("8345", ROGUE, "combat", 60) is None   # Era item is Druid-only


def test_class_limited_effect_is_ignored_for_other_classes(monkeypatch):
    monkeypatch.setitem(scorer.effects, "11815", {"name": "Hand of Justice", "stats": {"ap": 20}, "classes": [11]})
    hoj = scorer.items["11815"]
    assert scorer.score(hoj, "11815", {"ap": 1}, {}, "trinket", None, ROGUE) == 20  # item stat only
    assert scorer.score(hoj, "11815", {"ap": 1}, {}, "trinket", None, DRUID) == 40  # stat + effect


def test_strength_scores_for_enhancement_not_for_mage():
    reaper = "12784"  # Arcanite Reaper
    assert scorer.score_for(reaper, SHAMAN, "enhancement", 60) > 50
    assert scorer.score_for(reaper, MAGE, "frost", 60) is None  # mages cannot use axes


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
