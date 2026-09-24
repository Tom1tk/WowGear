"""WowGearBis (Classic Era) FastAPI application.

The gear lists are static files (frontend/data/gear/*.json, made by
scripts/data/build_gear.py). The API only does what needs the server:
the Blizzard character lookup, the realm list, and item scores.
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

app = FastAPI(title="WowGearBis Classic Era")
blizzard = BlizzardClient(settings.blizzard_client_id, settings.blizzard_client_secret)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.is_dir():  # on Vercel the frontend is served as static files instead
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
REGIONS = {"us", "eu", "kr", "tw"}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "game": "classic-era", "has_api_key": bool(settings.blizzard_client_id)}


def _region(value: str | None) -> str:
    region = (value or settings.default_region).strip().lower()
    if region not in REGIONS:
        raise HTTPException(status_code=422, detail="Unknown region.")
    return region


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


@app.get("/api/realms")
async def realms(region: str = "eu") -> dict:
    region = _region(region)
    try:
        return {"region": region, "realms": await blizzard.realms(region)}
    except BlizzardError as exc:
        _raise_http(exc)


@app.get("/api/character")
async def character(realm: str, name: str, region: str = "eu", spec: str | None = None) -> CharacterResult:
    region = _region(region)
    realm = realm.strip().lower()
    name = name.strip().lower()
    if not realm or not name:
        raise HTTPException(status_code=422, detail="Realm and character name are required.")
    try:
        summary, equipped, talents = await blizzard.character(region, realm, name)
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
