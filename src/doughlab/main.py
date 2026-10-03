"""FastAPI app di DoughLab."""
from __future__ import annotations

from contextlib import asynccontextmanager, suppress
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from ics import Calendar, Event

from .config import settings
from .db import init_db
from .services.fermentation import YEAST_PARAMS, YeastKind, suggest_yeast_pct
from .services.ingredients import STYLE_LABELS, RecipeIngredients, RecipeStyle, compute
from .services.presets import PRESETS, PRESETS_BY_KEY
from .services.scheduler import PHASE_LABELS, PhaseKind, PlanInput, PlanPhase, build_plan
from .services.thermal import CONTAINER_LABELS, ENVIRONMENT_LABELS, Container, Environment

STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def _common_ctx() -> dict:
    """Dropdown + metadati sempre serviti al template."""
    return {
        "app_name": settings.app_name,
        "yeast_kinds": [(k.value, YEAST_PARAMS[k].label) for k in YeastKind],
        "phase_kinds": [(k.value, PHASE_LABELS[k]) for k in PhaseKind],
        "containers": [(c.value, CONTAINER_LABELS[c]) for c in Container],
        "environments": [(e.value, ENVIRONMENT_LABELS[e]) for e in Environment],
        "styles": [(s.value, STYLE_LABELS[s]) for s in RecipeStyle],
        "presets": [{"key": p.key, "label": p.label, "style": p.style.value} for p in PRESETS],
    }


def _parse_phase_form(data: dict) -> list[PlanPhase]:
    """Legge campi index-based (phase_kind_0, phase_hours_0, ...)."""
    phases: list[PlanPhase] = []
    i = 0
    while f"phase_kind_{i}" in data:
        with suppress(ValueError, KeyError):
            phases.append(
                PlanPhase(
                    kind=PhaseKind(data[f"phase_kind_{i}"]),
                    label=data[f"phase_label_{i}"] or data[f"phase_kind_{i}"],
                    hours=float(data[f"phase_hours_{i}"] or 0),
                    ambient_c=float(data[f"phase_ambient_{i}"] or 22),
                    container=Container(data[f"phase_container_{i}"]),
                    environment=Environment(data[f"phase_env_{i}"]),
                )
            )
        i += 1
    return phases


def _parse_ingredients(data: dict) -> RecipeIngredients:
    def f(key: str, default: float) -> float:
        try:
            return float(data.get(key) or default)
        except ValueError:
            return default

    def pct(key: str, default_fraction: float) -> float:
        # L'interfaccia usa percentuali umane (es. 62, 2.8, 0.15), qui convertiamo in frazione.
        return f(key, default_fraction * 100.0) / 100.0

    def i(key: str, default: int) -> int:
        try:
            return int(float(data.get(key) or default))
        except ValueError:
            return default

    return RecipeIngredients(
        panetto_g=f("panetto_g", 250),
        n_panetti=i("n_panetti", 4),
        hydration_pct=pct("hydration_pct", 0.60),
        salt_pct=pct("salt_pct", 0.025),
        yeast_pct=pct("yeast_pct", 0.003),
        oil_pct=pct("oil_pct", 0.0),
        sugar_pct=pct("sugar_pct", 0.0),
        preferment_pct=pct("preferment_pct", 0.0),
        preferment_hydration_pct=pct("preferment_hydration_pct", 1.0),
    )


def _default_recipe_ctx() -> dict:
    """Dati per prima apertura: usa il primo preset come default."""
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    start_default = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    p = PRESETS[0]
    return {
        "start_at": start_default,
        "initial_dough_c": 24.0,
        "recipe_name": p.label,
        "style": p.style.value,
        "yeast_kind": p.yeast_kind.value,
        "target_work": p.target_work,
        "ingredients": asdict(p.ingredients),
        "phases": [
            {
                "kind": ph.kind.value, "label": ph.label, "hours": ph.hours,
                "ambient_c": ph.ambient_c, "container": ph.container.value,
                "environment": ph.environment.value,
            }
            for ph in p.phases
        ],
        "active_preset": p.key,
    }


def _preset_ctx(key: str) -> dict | None:
    p = PRESETS_BY_KEY.get(key)
    if p is None:
        return None
    ctx = _default_recipe_ctx()
    ctx.update(
        recipe_name=p.label,
        style=p.style.value,
        yeast_kind=p.yeast_kind.value,
        target_work=p.target_work,
        ingredients=asdict(p.ingredients),
        phases=[
            {
                "kind": ph.kind.value, "label": ph.label, "hours": ph.hours,
                "ambient_c": ph.ambient_c, "container": ph.container.value,
                "environment": ph.environment.value,
            }
            for ph in p.phases
        ],
        active_preset=p.key,
    )
    return ctx


def _compute_plan_and_ingredients(data: dict) -> dict:
    """Dalla form al pacchetto completo (plan + ingredienti + dati form)."""
    start_at = datetime.fromisoformat(data.get("start_at") or datetime.now().isoformat())
    initial_c = float(data.get("initial_dough_c") or 24)
    yeast_kind = YeastKind(data.get("yeast_kind") or YeastKind.FRESH.value)
    target_work = float(data.get("target_work") or 24)
    ingredients = _parse_ingredients(data)

    phases = _parse_phase_form(data)
    if not phases:
        phases = [PlanPhase(kind=PhaseKind.MIX, label="Impasto", hours=0.5, ambient_c=22,
                            container=Container.MASS_BOWL, environment=Environment.AMBIENT)]

    plan = build_plan(
        PlanInput(
            start_at=start_at,
            initial_dough_c=initial_c,
            phases=phases,
            yeast_kind=yeast_kind,
            yeast_pct=ingredients.yeast_pct,
            target_work=target_work,
        )
    )
    weights = compute(ingredients)
    suggested_pct = suggest_yeast_pct(plan.thermal, yeast_kind, target_work)

    return {
        "plan": plan,
        "weights": weights,
        "ingredients": ingredients,
        "suggested_pct": suggested_pct,
        "yeast_label": YEAST_PARAMS[yeast_kind].label,
        "yeast_kind": yeast_kind.value,
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    preset_key = request.query_params.get("preset")
    ctx = _common_ctx()
    recipe = _preset_ctx(preset_key) if preset_key else _default_recipe_ctx()
    if recipe is None:
        recipe = _default_recipe_ctx()
    ctx.update(recipe=recipe)
    return templates.TemplateResponse(request, "planner.html", ctx)


@app.post("/plan", response_class=HTMLResponse)
async def compute_plan(request: Request) -> HTMLResponse:
    form = await request.form()
    data = {k: str(v) for k, v in form.items()}
    bundle = _compute_plan_and_ingredients(data)
    ctx = _common_ctx()
    ctx.update(bundle)
    return templates.TemplateResponse(request, "partials/plan_result.html", ctx)


@app.post("/plan.ics")
async def plan_ics(request: Request) -> Response:
    form = await request.form()
    data = {k: str(v) for k, v in form.items()}
    bundle = _compute_plan_and_ingredients(data)
    plan = bundle["plan"]

    cal = Calendar()
    for pr in plan.phases:
        ev = Event()
        ev.name = f"🍕 {pr.phase.label}"
        ev.begin = pr.start_at
        ev.end = pr.end_at
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
