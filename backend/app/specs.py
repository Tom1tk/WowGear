"""Class/spec catalog with Icy Veins Best-in-Slot page slugs."""

# Icy Veins BiS page slug pattern: {spec}-{class}-pve-{role}-gear-best-in-slot
SPECS_BY_CLASS: dict[str, dict] = {
    "Warrior": {
        "specs": [
            {"name": "Arms", "slug": "arms-warrior-pve-dps-gear-best-in-slot"},
            {"name": "Fury", "slug": "fury-warrior-pve-dps-gear-best-in-slot"},
            {"name": "Protection", "slug": "protection-warrior-pve-tank-gear-best-in-slot"},
        ]
    },
    "Paladin": {
        "specs": [
            {"name": "Holy", "slug": "holy-paladin-pve-healer-gear-best-in-slot"},
            {"name": "Protection", "slug": "protection-paladin-pve-tank-gear-best-in-slot"},
            {"name": "Retribution", "slug": "retribution-paladin-pve-dps-gear-best-in-slot"},
        ]
    },
    "Hunter": {
        "specs": [
            {"name": "Beast Mastery", "slug": "beast-mastery-hunter-pve-dps-gear-best-in-slot"},
            {"name": "Marksmanship", "slug": "marksmanship-hunter-pve-dps-gear-best-in-slot"},
            {"name": "Survival", "slug": "survival-hunter-pve-dps-gear-best-in-slot"},
        ]
    },
    "Rogue": {
        "specs": [
            {"name": "Assassination", "slug": "assassination-rogue-pve-dps-gear-best-in-slot"},
            {"name": "Outlaw", "slug": "outlaw-rogue-pve-dps-gear-best-in-slot"},
            {"name": "Subtlety", "slug": "subtlety-rogue-pve-dps-gear-best-in-slot"},
        ]
    },
    "Priest": {
        "specs": [
            {"name": "Discipline", "slug": "discipline-priest-pve-healer-gear-best-in-slot"},
            {"name": "Holy", "slug": "holy-priest-pve-healer-gear-best-in-slot"},
            {"name": "Shadow", "slug": "shadow-priest-pve-dps-gear-best-in-slot"},
        ]
    },
    "Death Knight": {
        "specs": [
            {"name": "Blood", "slug": "blood-death-knight-pve-tank-gear-best-in-slot"},
            {"name": "Frost", "slug": "frost-death-knight-pve-dps-gear-best-in-slot"},
            {"name": "Unholy", "slug": "unholy-death-knight-pve-dps-gear-best-in-slot"},
        ]
    },
    "Shaman": {
        "specs": [
            {"name": "Elemental", "slug": "elemental-shaman-pve-dps-gear-best-in-slot"},
            {"name": "Enhancement", "slug": "enhancement-shaman-pve-dps-gear-best-in-slot"},
            {"name": "Restoration", "slug": "restoration-shaman-pve-healer-gear-best-in-slot"},
        ]
    },
    "Mage": {
        "specs": [
            {"name": "Arcane", "slug": "arcane-mage-pve-dps-gear-best-in-slot"},
            {"name": "Fire", "slug": "fire-mage-pve-dps-gear-best-in-slot"},
            {"name": "Frost", "slug": "frost-mage-pve-dps-gear-best-in-slot"},
        ]
    },
    "Warlock": {
        "specs": [
            {"name": "Affliction", "slug": "affliction-warlock-pve-dps-gear-best-in-slot"},
            {"name": "Demonology", "slug": "demonology-warlock-pve-dps-gear-best-in-slot"},
            {"name": "Destruction", "slug": "destruction-warlock-pve-dps-gear-best-in-slot"},
        ]
    },
    "Monk": {
        "specs": [
            {"name": "Brewmaster", "slug": "brewmaster-monk-pve-tank-gear-best-in-slot"},
            {"name": "Mistweaver", "slug": "mistweaver-monk-pve-healer-gear-best-in-slot"},
            {"name": "Windwalker", "slug": "windwalker-monk-pve-dps-gear-best-in-slot"},
        ]
    },
    "Druid": {
        "specs": [
            {"name": "Balance", "slug": "balance-druid-pve-dps-gear-best-in-slot"},
            {"name": "Feral", "slug": "feral-druid-pve-dps-gear-best-in-slot"},
            {"name": "Guardian", "slug": "guardian-druid-pve-tank-gear-best-in-slot"},
            {"name": "Restoration", "slug": "restoration-druid-pve-healer-gear-best-in-slot"},
        ]
    },
    "Demon Hunter": {
        "specs": [
            {"name": "Havoc", "slug": "havoc-demon-hunter-pve-dps-gear-best-in-slot"},
            {"name": "Vengeance", "slug": "vengeance-demon-hunter-pve-tank-gear-best-in-slot"},
        ]
    },
    "Evoker": {
        "specs": [
            {"name": "Devastation", "slug": "devastation-evoker-pve-dps-gear-best-in-slot"},
            {"name": "Preservation", "slug": "preservation-evoker-pve-healer-gear-best-in-slot"},
            {"name": "Augmentation", "slug": "augmentation-evoker-pve-dps-gear-best-in-slot"},
        ]
    },
}


def slug_for(class_name: str | None, spec_name: str | None) -> str | None:
    """Look up the Icy Veins BiS slug for a character's class + spec."""
    if not class_name or not spec_name:
        return None
    entry = SPECS_BY_CLASS.get(class_name)
    if not entry:
        return None
    for spec in entry["specs"]:
        if spec["name"].lower() == spec_name.lower():
            return spec["slug"]
    return None
