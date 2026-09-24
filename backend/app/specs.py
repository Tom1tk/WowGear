"""Find a Classic Era character's spec from its talent points."""

from .models import TalentTree
from .scoring import scorer

# Talent tree name (as the API returns it) -> spec key in data/era/classes.json
TREE_TO_SPEC = {
    "Feral Combat": "feral_cat",
    "Beast Mastery": "beast_mastery",
}


def detect_spec(class_id: int | None, level: int, talents: list[TalentTree]) -> tuple[str | None, str]:
    """(spec key, reason). Falls back to the class's leveling spec."""
    cls = scorer.classes.get(str(class_id)) if class_id else None
    if not cls:
        return None, "Unknown class."
    default = scorer.weights["leveling_default"][cls["slug"]]
    spent = [t for t in talents if t.points > 0]
    if not spent:
        reason = ("No talent points yet (they start at level 10)." if level < 10
                  else "No talent data from Blizzard.")
        return default, f"{reason} Using the usual leveling spec: {cls['specs'][default]['name']}."
    top = max(spent, key=lambda t: t.points)
    key = TREE_TO_SPEC.get(top.name, top.name.lower().replace(" ", "_"))
    if key not in cls["specs"]:
        return default, f"Talent tree '{top.name}' is not known. Using {cls['specs'][default]['name']}."
    points = ", ".join(f"{t.name} {t.points}" for t in talents)
    reason = f"Most talent points in {top.name} ({points})."
    if key == "feral_cat":
        reason += " Choose Feral (Bear) if you tank."
    return key, reason
