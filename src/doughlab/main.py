"""FastAPI app di DoughLab."""
from __future__ import annotations

from contextlib import asynccontextmanager, suppress
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


DEFAULT_PHASES: list[dict] = [
    {
        "kind": PhaseKind.MIX,
        "label": "Impasto",
        "hours": 0.5,
        "ambient_c": 22.0,
        "container": Container.MASS_BOWL,
        "environment": Environment.AMBIENT,
    },
    {
        "kind": PhaseKind.BULK,
        "label": "Puntata",
        "hours": 2.0,
        "ambient_c": 22.0,
        "container": Container.MASS_BOWL,
        "environment": Environment.AMBIENT,
    },
    {
        "kind": PhaseKind.MATURATION,
        "label": "Maturazione in frigo",
        "hours": 24.0,
        "ambient_c": 4.0,
        "container": Container.MASS_BOX,
        "environment": Environment.FRIDGE_HOME,
    },
    {
        "kind": PhaseKind.TEMPER,
        "label": "Cambio temperatura",
        "hours": 2.0,
        "ambient_c": 22.0,
        "container": Container.MASS_BOX,
        "environment": Environment.AMBIENT,
    },
    {
        "kind": PhaseKind.SHAPE,
        "label": "Staglio",
        "hours": 0.5,
        "ambient_c": 22.0,
        "container": Container.BALLS_BOX,
        "environment": Environment.AMBIENT,
    },
    {
        "kind": PhaseKind.PROOF,
        "label": "Appretto",
        "hours": 4.0,
        "ambient_c": 22.0,
        "container": Container.BALLS_BOX,
        "environment": Environment.AMBIENT,
    },
]


def _parse_phase_form(data: dict) -> list[PlanPhase]:
    """Parsing del form (array parallelo di campi index-based)."""
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


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    start_default = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    ctx = {
        "app_name": settings.app_name,
        "default_phases": DEFAULT_PHASES,
        "start_default": start_default,
        "yeast_kinds": [(k.value, YEAST_PARAMS[k].label) for k in YeastKind],
        "phase_kinds": [(k.value, PHASE_LABELS[k]) for k in PhaseKind],
        "containers": [(c.value, CONTAINER_LABELS[c]) for c in Container],
        "environments": [(e.value, ENVIRONMENT_LABELS[e]) for e in Environment],
    }
    return templates.TemplateResponse(request, "planner.html", ctx)


@app.post("/plan", response_class=HTMLResponse)
async def compute_plan(request: Request) -> HTMLResponse:
    form = await request.form()
    data = {k: str(v) for k, v in form.items()}

    start_at = datetime.fromisoformat(data.get("start_at") or datetime.now().isoformat())
    initial_c = float(data.get("initial_dough_c") or 24)
    yeast_kind = YeastKind(data.get("yeast_kind") or YeastKind.FRESH.value)
    yeast_pct = float(data.get("yeast_pct") or 0.3)
    target_work = float(data.get("target_work") or 24)

    phases = _parse_phase_form(data)
    if not phases:
        phases = [PlanPhase(**p) for p in DEFAULT_PHASES]  # type: ignore[arg-type]

    plan = build_plan(
        PlanInput(
            start_at=start_at,
            initial_dough_c=initial_c,
            phases=phases,
            yeast_kind=yeast_kind,
            yeast_pct=yeast_pct,
            target_work=target_work,
        )
    )

    suggested = suggest_yeast_pct(plan.thermal, yeast_kind, target_work)

    return templates.TemplateResponse(
        request,
        "partials/plan_result.html",
        {
            "plan": plan,
            "yeast_pct": yeast_pct,
            "suggested_pct": suggested,
            "yeast_label": YEAST_PARAMS[yeast_kind].label,
        },
    )


@app.post("/plan.ics")
async def plan_ics(request: Request) -> Response:
    form = await request.form()
    data = {k: str(v) for k, v in form.items()}
    start_at = datetime.fromisoformat(data.get("start_at") or datetime.now().isoformat())
    initial_c = float(data.get("initial_dough_c") or 24)
    yeast_kind = YeastKind(data.get("yeast_kind") or YeastKind.FRESH.value)
    yeast_pct = float(data.get("yeast_pct") or 0.3)
    target_work = float(data.get("target_work") or 24)
    phases = _parse_phase_form(data) or [PlanPhase(**p) for p in DEFAULT_PHASES]  # type: ignore[arg-type]

    plan = build_plan(
        PlanInput(
            start_at=start_at,
            initial_dough_c=initial_c,
            phases=phases,
            yeast_kind=yeast_kind,
            yeast_pct=yeast_pct,
            target_work=target_work,
        )
    )

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
