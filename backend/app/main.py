"""WowGearBis (WoW Forever) FastAPI application.

The gear lists are static files (frontend/data/gear/*.json, made by
scripts/data/build_gear.py). The API only does what needs the server:
the Blizzard character lookup, and item scores.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .blizzard import (
    ApiKeyInvalidError,
    ApiKeyMissingError,
    BlizzardClient,
    BlizzardError,
    CharacterNotFoundError,
    RateLimitedError,
)
from .config import settings
from .models import CharacterResult, ScoreRequest
from .scoring import scorer
from .specs import detect_spec

app = FastAPI(title="WowGearBis WoW Forever")
blizzard = BlizzardClient(settings.blizzard_client_id, settings.blizzard_client_secret)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.is_dir():  # on Vercel the frontend is served as static files instead
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
REGIONS = {"us", "eu", "kr", "tw"}
MAX_NAME = 24


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "game": "forever", "has_api_key": bool(settings.blizzard_client_id)}


def _region(value: str | None) -> str:
    region = (value or settings.default_region).strip().lower()
    if region not in REGIONS:
        raise HTTPException(status_code=422, detail="Unknown region.")
    return region


def _name(value: str, label: str) -> str:
    value = value.strip().lower()
    if not value or len(value) > MAX_NAME or not value.isalpha():  # isalpha: unicode letters
        raise HTTPException(status_code=422, detail=f"{label} must be 1-{MAX_NAME} letters.")
    return value


def _raise_http(exc: BlizzardError):
    if isinstance(exc, ApiKeyMissingError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, CharacterNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, RateLimitedError):
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    if isinstance(exc, ApiKeyInvalidError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/character")
async def character(name: str, surname: str, region: str = "eu", spec: str | None = None) -> CharacterResult:
    region = _region(region)
    name, surname = _name(name, "First name"), _name(surname, "Surname")
    try:
        summary, equipped, talents = await blizzard.character(region, name, surname)
    except BlizzardError as exc:
        _raise_http(exc)
    detected, reason = detect_spec(summary.class_id, summary.level, talents)
    chosen = spec or detected
    cls_id = str(summary.class_id) if summary.class_id else None
    if chosen and cls_id and cls_id in scorer.classes and chosen in scorer.classes[cls_id]["specs"]:
        for item in equipped.values():
            item.score = scorer.score_for(str(item.item_id), cls_id, chosen, summary.level,
                                          str(summary.race_id) if summary.race_id else None)
    return CharacterResult(character=summary, equipped=equipped, talents=talents,
                           spec=detected, spec_reason=reason)


@app.post("/api/score")
async def score(request: ScoreRequest) -> dict:
    """Scores of items for a class/spec/level (used when the user changes spec)."""
    cls_id = str(request.class_id)
    if cls_id not in scorer.classes or request.spec not in scorer.classes[cls_id]["specs"]:
        raise HTTPException(status_code=422, detail="Unknown class or spec.")
    race = str(request.race_id) if request.race_id else None
    return {"scores": {str(i): scorer.score_for(str(i), cls_id, request.spec, request.level, race)
                       for i in request.item_ids[:40]}}
