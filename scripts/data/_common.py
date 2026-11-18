"""Shared helpers for the offline data pipeline (scripts/data)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
FOREVER = ROOT / "data" / "forever"
STAGING = FOREVER / "staging"
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


_TOKEN = re.compile(r"""\s*(?:(?P<str>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")|(?P<num>-?\d+(?:\.\d+)?)|(?P<word>nil|true|false)|(?P<p>[{}=,\[\]]))""")


def lua_value(text: str, pos: int = 0):
    """Parse one Lua literal (table/string/number/nil) from text[pos:]; -> (value, new_pos).
    Tables become lists (positional) or dicts (keyed); nil becomes None."""
    m = _TOKEN.match(text, pos)
    if not m:
        raise ValueError(f"bad Lua at {pos}: {text[pos:pos + 30]!r}")
    pos = m.end()
    if m.group("str"):
        return re.sub(r"\\(.)", r"\1", m.group("str")[1:-1]), pos
    if m.group("num"):
        n = m.group("num")
        return (float(n) if "." in n else int(n)), pos
    if m.group("word"):
        return {"nil": None, "true": True, "false": False}[m.group("word")], pos
    if m.group("p") != "{":
        raise ValueError(f"unexpected {m.group('p')!r} at {pos}")
    items, keyed = [], {}
    while True:
        m = _TOKEN.match(text, pos)
        if m and m.group("p") == "}":
            pos = m.end()
            break
        if m and m.group("p") == ",":
            pos = m.end()
            continue
        ident = re.compile(r"\s*([A-Za-z_]\w*)\s*=").match(text, pos)
        if ident and not (m and m.group("word")):
            keyed[ident.group(1)], pos = lua_value(text, ident.end())
            continue
        if m and m.group("p") == "[":
            key, pos = lua_value(text, m.end())
            pos = _TOKEN.match(text, pos).end()  # ]
            pos = _TOKEN.match(text, pos).end()  # =
            keyed[key], pos = lua_value(text, pos)
            continue
        val, pos = lua_value(text, pos)
        items.append(val)
    return (keyed if keyed and not items else items), pos
