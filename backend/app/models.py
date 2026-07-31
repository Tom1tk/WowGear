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
    # Blizzard inventory type, e.g. "WEAPON", "TWOHWEAPON", "SHIELD" — used to
    # suppress off-hand advice when the main hand is two-handed.
    inventory_type: str | None = None


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


class TextSegment(BaseModel):
    """One piece of rendered text, optionally a hyperlink (href)."""
    text: str
    url: str | None = None


class BisItem(BaseModel):
    slot: str
    item_id: int
    name: str
    ilvl: int
    track: str | None = None
    drop: str = ""
    drop_links: list[str] = Field(default_factory=list)
    drop_link_texts: list[str] = Field(default_factory=list)
    # WoW bonus ids from the page's data-wowhead attribute, e.g. [13786].
    bonus: list[int] = Field(default_factory=list)
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
    # Linked rendering: concatenating segment texts yields exactly
    # `title` / `detail`; a non-null url makes that segment a hyperlink.
    title_segments: list[TextSegment] = Field(default_factory=list)
    detail_segments: list[TextSegment] = Field(default_factory=list)


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
