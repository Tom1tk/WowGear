"""Shared data models for WowGearBis (WoW Forever)."""

from pydantic import BaseModel, ConfigDict, Field


class WornWeapon(BaseModel):
    dps: float
    speed: float


class WornItem(BaseModel):
    """A worn item's stats as Blizzard reports them (random-stat rolls included). Used only to score it."""
    model_config = ConfigDict(populate_by_name=True)
    name: str = Field(max_length=200)
    item_class: int = Field(alias="class")
    subclass: int
    inventory_type: str = Field(max_length=40)
    stats: dict[str, float] = Field(default_factory=dict)
    weapon: WornWeapon | None = None


class EquippedItem(BaseModel):
    slot: str
    item_id: int
    name: str
    quality: str | None = None
    inventory_type: str | None = None
    enchant: str | None = None
    worn: WornItem | None = None
    score: float | None = None  # filled in for the chosen spec


class TalentTree(BaseModel):
    name: str
    points: int


class CharacterSummary(BaseModel):
    name: str
    surname: str | None = None
    region: str
    level: int = 0
    faction: str | None = None  # "A" | "H"
    race: str | None = None
    race_id: int | None = None
    class_name: str | None = None
    class_id: int | None = None
    guild: str | None = None
    avatar_url: str | None = None
    ruleset: str | None = None  # e.g. Normal / PvP / RP


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
    worn: dict[str, WornItem] = Field(default_factory=dict)  # item id -> stats read from the character
