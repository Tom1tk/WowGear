"""Shared data models for WowGearBis (Classic Era)."""

from pydantic import BaseModel, Field


class EquippedItem(BaseModel):
    slot: str
    item_id: int
    name: str
    quality: str | None = None
    inventory_type: str | None = None
    enchant: str | None = None
    score: float | None = None  # filled in for the chosen spec


class TalentTree(BaseModel):
    name: str
    points: int


class CharacterSummary(BaseModel):
    name: str
    realm: str
    region: str
    level: int = 0
    faction: str | None = None  # "A" | "H"
    race: str | None = None
    race_id: int | None = None
    class_name: str | None = None
    class_id: int | None = None
    guild: str | None = None
    avatar_url: str | None = None


class CharacterResult(BaseModel):
    character: CharacterSummary
    equipped: dict[str, EquippedItem]
    talents: list[TalentTree] = Field(default_factory=list)
    spec: str | None = None           # detected spec key, e.g. "feral_cat"
    spec_reason: str = ""


class ScoreRequest(BaseModel):
    class_id: int
    spec: str
    level: int = 60
    race_id: int | None = None
    item_ids: list[int] = Field(default_factory=list)
