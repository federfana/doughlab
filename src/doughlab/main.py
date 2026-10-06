"""FastAPI app di DoughLab."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from ics import Calendar, Event

from . import diary, flours, recipes
from .config import settings
from .db import init_db
from .planning import compute_plan_and_ingredients, default_recipe_ctx, preset_ctx
from .services.fermentation import YeastKind
from .services.scheduler import PHASE_LABELS, PhaseKind
from .services.thermal import CONTAINER_LABELS, ENVIRONMENT_LABELS
from .web import STATIC_DIR, common_ctx, templates


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    added = await init_db()
    await flours.seed_if_empty()
    if ("flours", "method") in added:
        await flours.backfill_builtin_methods()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(diary.router)
app.include_router(recipes.router)
app.include_router(flours.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    preset_key = request.query_params.get("preset")
    selected_yeast = request.query_params.get("yeast")
    selected_oven = request.query_params.get("oven", "split")
    if selected_oven == "nettuno":
        selected_oven = "split"
    if selected_oven not in {"home", "split"}:
        selected_oven = "split"
    try:
        yeast_kind = YeastKind(selected_yeast) if selected_yeast else None
    except ValueError:
        yeast_kind = None
    ctx = common_ctx()
    recipe = preset_ctx(preset_key, yeast_kind, selected_oven) if preset_key else default_recipe_ctx()
    if recipe is None:
        recipe = default_recipe_ctx()
    loaded = None
    recipe_id, version = request.query_params.get("recipe", ""), request.query_params.get("version", "")
    if recipe_id.isdecimal() and len(recipe_id) < 10:
        saved = await recipes.load_recipe(int(recipe_id), int(version) if version.isdecimal() else None)
        if saved is not None:
            recipe, loaded = saved, saved.pop("saved_recipe")
    ctx.update(recipe=recipe, **await diary.panel_context())
    ctx.update(await recipes.panel_context(loaded=loaded))
    ctx.update(await flours.panel_context())
    return templates.TemplateResponse(request, "planner.html", ctx)


async def _plan_bundle(data: dict[str, str]) -> dict[str, Any]:
    """Piano più miscela di farine scelta (statistiche e idratazione consigliata)."""
    bundle = compute_plan_and_ingredients(data)
    hydration_pct = bundle["ingredients"].hydration_pct * 100
    has_preferment = bundle["ingredients"].preferment_pct > 0 or any(
        phase.phase.kind == PhaseKind.PREFERMENT for phase in bundle["plan"].phases
    )
    bundle.update(await flours.blend_context(data, hydration_pct, has_preferment))
    bundle["plan_snapshot"].update(flours.snapshot_extras(bundle["flour_blend"]))
    return bundle


@app.post("/plan", response_class=HTMLResponse)
async def compute_plan(request: Request) -> HTMLResponse:
    form = await request.form()
    data = {k: str(v) for k, v in form.items()}
    ctx = common_ctx()
    ctx.update(await _plan_bundle(data))
    return templates.TemplateResponse(request, "partials/plan_result.html", ctx)


@app.post("/diario/da-piano", response_class=HTMLResponse)
async def diary_from_plan(request: Request) -> HTMLResponse:
    """Apre il modulo del diario precompilato con il piano mostrato nel pianificatore."""
    form = await request.form()
    data = {k: str(v) for k, v in form.items()}
    snapshot = (await _plan_bundle(data))["plan_snapshot"]
    ctx = common_ctx()
    ctx.update(await diary.panel_context(form=diary.form_from_plan(snapshot)))
    return templates.TemplateResponse(request, "partials/diary_panel.html", ctx)


@app.post("/plan.ics")
async def plan_ics(request: Request) -> Response:
    form = await request.form()
    data = {k: str(v) for k, v in form.items()}
    bundle = compute_plan_and_ingredients(data)
    plan = bundle["plan"]

    cal = Calendar()
    for pr in plan.phases:
        ev = Event()
        ev.name = f"🍕 {pr.phase.label}"
        # Senza fuso la libreria ics scrive l'ora come UTC e il calendario la sposta.
        ev.begin = pr.start_at.astimezone()
        ev.end = pr.end_at.astimezone()
        ev.description = (
            f"Fase: {PHASE_LABELS[pr.phase.kind]}\n"
            f"Temp. ambiente: {pr.phase.ambient_c:.1f} °C\n"
            f"Contenitore: {CONTAINER_LABELS[pr.phase.container]}\n"
            f"Ambiente: {ENVIRONMENT_LABELS[pr.phase.environment]}\n"
            f"Maturità: {pr.maturity_start_pct:.0f}% → {pr.maturity_end_pct:.0f}%"
        )
        cal.events.add(ev)

    return Response(
        content=cal.serialize(),
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="doughlab-plan.ics"'},
    )
