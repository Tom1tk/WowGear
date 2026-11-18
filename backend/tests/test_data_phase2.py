"""Phase 2 data: unscored listing, set-bonus spreading, quest chains, Lua parsing, set bonus text (invented ids)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "data"))

import merge  # noqa: E402
import parse_blizzard as pb  # noqa: E402
import parse_questie as pq  # noqa: E402
from _common import lua_value  # noqa: E402
from app.scoring import scorer  # noqa: E402


def test_unscored_lists_unweighted_stats_and_random_enchant():
    out = merge.unscored_lines({"agi": 5, "res_fire": 10}, [], [], random=True, is_scored=lambda k: k == "agi")
    assert any("10" in u for u in out) and not any("5" in u for u in out)
    assert any(u.startswith("Random enchant") for u in out)


def test_build_chains_positions():
    q = {1: {"name": "A", "level": 10, "pre": [], "next": 2}, 2: {"name": "B", "level": 11, "pre": [1], "next": 3},
         3: {"name": "C", "level": 12, "pre": [2], "next": None}, 9: {"name": "Solo", "level": 5, "pre": [], "next": None}}
    c = pq.build_chains(q)
    assert c[3] == {"pos": 3, "len": 3, "first_id": 1, "first_name": "A", "first_level": 10}
    assert c[1]["pos"] == 1 and c[1]["len"] == 3 and 9 not in c


def test_lua_value_tables_and_keys():
    v, _ = lua_value('{1,"a b",nil,{[5]=2,k=3}}', 0)
    assert v[0] == 1 and v[1] == "a b" and v[2] is None and v[3] == {5: 2, "k": 3}


def test_set_bonus_spreads_over_equippable_pieces(monkeypatch):
    def piece(cls_mask_ok=True):
        return {"class": 4, "subclass": 0, "inventory_type": "FINGER", "stats": {}, "set": "990001", "quality": 3}
    monkeypatch.setitem(scorer.items, "990011", piece())
    monkeypatch.setitem(scorer.items, "990012", piece())
    monkeypatch.setitem(scorer.sets, "990001", {"name": "Invented Set", "pieces": [990011, 990012, 990013],
        "bonuses": [{"count": 2, "text": "+20 Attack Power.", "stats": {"ap": 20}, "scored": True},
                    {"count": 3, "text": "+10 Attack Power.", "stats": {"ap": 10}, "scored": True}]})
    it = scorer.items["990011"]
    druid = "11"
    bonuses = scorer.set_bonuses_for(it, druid)
    assert [b["scored"] for b in bonuses] == [True, False]  # 3rd piece is not in our data
    assert scorer.score(it, "990011", {"ap": 1}, {}, "ring", None, druid) == 0  # raw ignores sets
    assert scorer.score(it, "990011", {"ap": 1}, {}, "ring", None, druid, bonus=True) == 10  # 20 / 2 pieces


def test_parse_set_bonus_stat_and_non_stat():
    assert pb.parse_set_bonus("+14 Attack Power.")
    assert pb.parse_set_bonus("Invented proc text that is not a stat.") is None
