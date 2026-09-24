"""Shared helpers for the offline data pipeline (scripts/data)."""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
STAGING = ROOT / "data" / "era" / "staging"
ERA = ROOT / "data" / "era"
REPORTS = ROOT / "reports"


def load_env() -> None:
    """Load KEY=VALUE lines from .env into os.environ (no dependency)."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def write_json(path: Path, data, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        if compact:
            json.dump(data, fh, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        else:
            json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")


def read_json(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)
