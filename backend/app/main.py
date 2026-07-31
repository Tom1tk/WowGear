"""WowGearBis FastAPI application."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .armory import (
    ArmoryCharacterNotFoundError,
    ArmoryError,
    ArmoryParseError,
    fetch_armory_page,
    parse_armory_page,
)
from .blizzard import (
    ApiKeyInvalidError,
    ApiKeyMissingError,
    ApiUnavailableError,
    BlizzardClient,
    BlizzardError,
    CharacterNotFoundError,
    RateLimitedError,
)
from .config import settings
from .icyveins import BisPageFetcher, IcyVeinsError, PageNotFoundError, ParseError, parse_bis_page
from .models import AnalyzeRequest, AnalyzeResult
from .recommend import analyze_gear, catchup_action
from .specs import SPECS_BY_CLASS, slug_for

app = FastAPI(title="WowGearBis")

blizzard = BlizzardClient(settings.blizzard_client_id, settings.blizzard_client_secret)
bis_fetcher = BisPageFetcher(ttl_seconds=settings.icyveins_ttl_seconds)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "has_api_key": bool(settings.blizzard_client_id)}


@app.get("/api/specs")
async def specs() -> dict:
    return SPECS_BY_CLASS


@app.post("/api/analyze")
async def analyze(request: AnalyzeRequest) -> AnalyzeResult:
    region = (request.region or settings.default_region).strip().lower()
    realm = request.realm.strip().lower()
    character = request.character.strip().lower()
    if not realm or not character:
        raise HTTPException(status_code=422, detail="realm and character are required")

    try:
        summary = await blizzard.character_summary(region, realm, character)
        equipped = await blizzard.equipment(region, realm, character)
        source = "blizzard"
    except (ApiKeyMissingError, ApiUnavailableError):
        # Keyless fallback: scrape the public Armory page instead.
        try:
            page = await fetch_armory_page(region, realm, character)
        except ArmoryCharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ArmoryError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        try:
            summary, equipped = parse_armory_page(page, region)
        except ArmoryParseError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        source = "armory"
    except ApiKeyInvalidError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except CharacterNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RateLimitedError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except BlizzardError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    slug = request.spec or slug_for(summary.class_name, summary.spec)
    if not slug:
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not detect a specialization for this character — "
                "please select one in the UI."
            ),
        )

    try:
        page = await bis_fetcher.fetch(slug)
    except PageNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IcyVeinsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        bis_items, page_max_ilvl, farm_tips = parse_bis_page(page)
    except ParseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    bis_max_ilvl = page_max_ilvl or settings.bis_max_ilvl
    comparisons, actions = analyze_gear(equipped, bis_items, bis_max_ilvl)

    catchup = catchup_action(summary.average_item_level, bis_max_ilvl)
    if catchup:
        actions.append(catchup)
    actions.sort(key=lambda action: action.urgency, reverse=True)
    for rank, action in enumerate(actions[: settings.actions_limit], start=1):
        action.rank = rank

    spec_label = slug.replace("-gear-best-in-slot", "").replace("-", " ").title()

    return AnalyzeResult(
        character=summary,
        comparisons=comparisons,
        actions=actions[: settings.actions_limit],
        farm_tips=farm_tips,
        bis_url=f"https://www.icy-veins.com/wow/{slug}",
        bis_max_ilvl=bis_max_ilvl,
        spec_label=spec_label,
        source=source,
    )
