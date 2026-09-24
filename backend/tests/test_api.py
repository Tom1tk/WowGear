"""API endpoints with the Blizzard client replaced by a fake."""

from fastapi.testclient import TestClient

from app import main
from app.blizzard import CharacterNotFoundError
from app.models import CharacterSummary, EquippedItem, TalentTree

client = TestClient(main.app)


def test_health():
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["game"] == "classic-era"


def test_score_endpoint():
    body = client.post("/api/score", json={"class_id": 7, "spec": "enhancement", "level": 60,
                                           "item_ids": [12784, 999999]}).json()
    assert body["scores"]["12784"] > 0 and body["scores"]["999999"] is None


def test_score_rejects_unknown_spec():
    assert client.post("/api/score", json={"class_id": 7, "spec": "fury"}).status_code == 422


def test_character_detects_spec_and_scores_items(monkeypatch):
    async def fake(region, realm, name):
        summary = CharacterSummary(name="Testchar", realm="Whitemane", region=region, level=60,
                                   faction="H", race="Tauren", race_id=6, class_name="Shaman", class_id=7)
        equipped = {"two_hand": EquippedItem(slot="two_hand", item_id=12784, name="Arcanite Reaper")}
        talents = [TalentTree(name="Elemental", points=5), TalentTree(name="Enhancement", points=31),
                   TalentTree(name="Restoration", points=15)]
        return summary, equipped, talents

    monkeypatch.setattr(main.blizzard, "character", fake)
    body = client.get("/api/character", params={"region": "us", "realm": "whitemane", "name": "testchar"}).json()
    assert body["spec"] == "enhancement"
    assert body["equipped"]["two_hand"]["score"] > 0


def test_character_not_found(monkeypatch):
    async def fake(region, realm, name):
        raise CharacterNotFoundError("Character not found")

    monkeypatch.setattr(main.blizzard, "character", fake)
    resp = client.get("/api/character", params={"region": "eu", "realm": "x", "name": "y"})
    assert resp.status_code == 404


def test_bad_region():
    assert client.get("/api/realms", params={"region": "mars"}).status_code == 422
