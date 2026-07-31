"""Shared data models for WowGearBis."""

from pydantic import BaseModel, Field

SLOTS = [
    "head", "neck", "shoulders", "back", "chest", "wrist", "hands", "waist",
    "legs", "feet", "ring_1", "ring_2", "trinket_1", "trinket_2",
    "main_hand", "off_hand",
]

SLOT_LABELS = {
    "head": "Head", "neck": "Neck", "shoulders": "Shoulders", "back": "Back",
    "chest": "Chest", "wrist": "Wrist", "hands": "Hands", "waist": "Waist",
    "legs": "Legs", "feet": "Feet", "ring_1": "Ring 1", "ring_2": "Ring 2",
    "trinket_1": "Trinket 1", "trinket_2": "Trinket 2",
    "main_hand": "Main Hand", "off_hand": "Off Hand",
}


class EquippedItem(BaseModel):
    slot: str
    item_id: int
    name: str
    ilvl: int
    quality: str | None = None
    enchant: str | None = None
    icon_url: str | None = None


class CharacterSummary(BaseModel):
    name: str
    realm: str
    region: str
    faction: str | None = None
    race: str | None = None
    class_name: str | None = None
    spec: str | None = None
    level: int | None = None
    average_item_level: int | None = None
    achievement_points: int | None = None
    mythic_plus_rating: int | None = None
    avatar_url: str | None = None
    render_url: str | None = None


class BisItem(BaseModel):
    slot: str
    item_id: int
    name: str
    ilvl: int
    track: str | None = None
    drop: str = ""
    drop_links: list[str] = Field(default_factory=list)
    drop_link_texts: list[str] = Field(default_factory=list)
    enchant: str | None = None
    gems: list[str] = Field(default_factory=list)


class SlotComparison(BaseModel):
    slot: str
    slot_label: str
    equipped: EquippedItem | None = None
    bis: BisItem | None = None
    status: str  # match | upgrade | ahead | empty | no_bis
    ilvl_gap: int | None = None


class Action(BaseModel):
    rank: int = 0
    slot: str = ""
    category: str  # gear | upgrade | craft | catchup
    title: str
    detail: str
    urgency: float
    target_item: str | None = None
    target_ilvl: int | None = None


class FarmTip(BaseModel):
    title: str
    text: str


class AnalyzeRequest(BaseModel):
    region: str = "eu"
    realm: str
    character: str
    spec: str | None = None


class AnalyzeResult(BaseModel):
    character: CharacterSummary
    comparisons: list[SlotComparison]
    actions: list[Action]
    farm_tips: list[FarmTip]
    bis_url: str
    bis_max_ilvl: int
    spec_label: str
    source: str = "blizzard"  # blizzard | armory
