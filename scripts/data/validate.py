"""Check the generated Forever gear files against the class rules and required ids.

Writes reports/validation.md and exits 1 on any rule violation.

    python scripts/data/validate.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
from _common import FOREVER, REPORTS, ROOT, read_json  # noqa: E402
from app.scoring import scorer  # noqa: E402

GEAR = ROOT / "frontend" / "data" / "gear"
REQUIRED = {"273088": "", "270043": "", "270032": "", "284715": "", "280766": "", "271766": "", "263411": ""}


def main() -> int:
    items = read_json(FOREVER / "items.json")
    files = sorted(GEAR.glob("*.json"))
    problems, scored, ids = [], 0, set()
    for path in files:
        data = read_json(path)
        cls = str(data["class_id"])
        for slot, points in data["slots"].items():
            for pt in points:
                for iid, _ in pt["items"]:
                    scored += 1
                    ids.add(iid)
                    it = scorer.items.get(iid)
                    usable = it and scorer.usable_from(it, cls)
                    if not it or usable is None or usable > pt["level"] or scorer.min_level(it) > pt["level"]:
                        problems.append(f"{path.stem} {slot} L{pt['level']}: item {iid} not usable")
        for iid, it in data["items"].items():
            for s in it["sources"]:
                if s.get("conflict") and not s.get("conflict_reason"):
                    problems.append(f"{path.stem}: item {iid} source conflict without reason")
    lines = ["# Validation", "", f"- gear files: {len(files)}", f"- distinct scored items: {len(ids)}",
             f"- slot entries checked: {scored}", f"- rule violations: {len(problems)}", ""]
    lines += [f"- {p}" for p in problems[:50]]
    lines += ["", "## Required ids", ""]
    for iid in REQUIRED:
        state = ("in items.json" if iid in items else "not in items.json (crawl may not have reached it)")
        lines.append(f"- {iid}: {state}; scored in {'some gear file' if iid in ids else 'no gear file'}")
    (REPORTS / "validation.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
