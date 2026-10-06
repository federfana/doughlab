"""FastAPI app di DoughLab."""
from __future__ import annotations

import json
import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from ics import Calendar, Event
from sqlalchemy import select

from .config import settings
from .db import SessionLocal, init_db
from .models import Bake
from .services.fermentation import (
    DEFAULT_TARGET_WORK,
    YEAST_PARAMS,
    YeastKind,
    suggest_yeast_pct,
)
from .services.ingredients import STYLE_LABELS, RecipeIngredients, RecipeStyle, compute
from .services.presets import PRESETS, PRESETS_BY_KEY, Preset
from .services.scheduler import (
    PHASE_LABELS,
    PhaseKind,
    PlanInput,
    PlanPhase,
    build_plan,
    fermentation_activity_mask,
)
from .services.thermal import CONTAINER_LABELS, ENVIRONMENT_LABELS, Container, Environment

STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"
WEEKDAYS_IT = ("lun", "mar", "mer", "gio", "ven", "sab", "dom")
MONTHS_IT = (
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
)
YEAST_SHORT_LABELS = {
    YeastKind.FRESH: "Fresco",
    YeastKind.DRY: "Secco",
    YeastKind.SOURDOUGH: "Madre",
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def _common_ctx() -> dict[str, Any]:
    """Dropdown + metadati sempre serviti al template."""
    return {
        "app_name": settings.app_name,
        "yeast_kinds": [
            (k.value, YEAST_SHORT_LABELS[k], YEAST_PARAMS[k].label) for k in YeastKind
        ],
        "phase_kinds": [(k.value, PHASE_LABELS[k]) for k in PhaseKind],
        "containers": [(c.value, CONTAINER_LABELS[c]) for c in Container],
        "environments": [(e.value, ENVIRONMENT_LABELS[e]) for e in Environment],
        "styles": [(s.value, STYLE_LABELS[s]) for s in RecipeStyle],
        "presets": [
            {
                "key": p.key,
                "label": p.label,
                "style": p.style.value,
                "description": p.description,
                "flour_hint": p.flour_hint,
            }
            for p in PRESETS
        ],
        "weekdays_it": WEEKDAYS_IT,
        "months_it": MONTHS_IT,
    }


# Gli stessi limiti degli input HTML: il server non si fida del client.
MAX_PHASES = 30


def _number(data: dict[str, str], key: str, default: float, low: float, high: float) -> float:
    """Numero finito dentro [low, high]; valori assenti, illeggibili o NaN/inf danno `default`."""
    try:
        value = float(data.get(key) or default)
    except ValueError:
        return default
    return min(high, max(low, value)) if math.isfinite(value) else default


def _parse_phase_form(data: dict[str, str]) -> list[PlanPhase]:
    """Legge campi index-based (phase_kind_0, phase_hours_0, ...)."""
    phases: list[PlanPhase] = []
    i = 0
    while f"phase_kind_{i}" in data and i < MAX_PHASES:
        with suppress(ValueError, KeyError):
            phases.append(
                PlanPhase(
                    kind=PhaseKind(data[f"phase_kind_{i}"]),
                    label=(data[f"phase_label_{i}"] or data[f"phase_kind_{i}"])[:80],
                    hours=_number(data, f"phase_hours_{i}", 0, 0, 720),
                    ambient_c=_number(data, f"phase_ambient_{i}", 22, -5, 50),
                    container=Container(data[f"phase_container_{i}"]),
                    environment=Environment(data[f"phase_env_{i}"]),
                )
            )
        i += 1
    return phases


def _parse_ingredients(data: dict[str, str]) -> RecipeIngredients:
    def pct(key: str, default_fraction: float, low: float, high: float) -> float:
        # L'interfaccia usa percentuali umane (es. 62, 2.8, 0.15), qui convertiamo in frazione.
        return _number(data, key, default_fraction * 100.0, low, high) / 100.0

    return RecipeIngredients(
        panetto_g=_number(data, "panetto_g", 250, 30, 2000),
        n_panetti=int(_number(data, "n_panetti", 4, 1, 200)),
        hydration_pct=pct("hydration_pct", 0.60, 40, 120),
        salt_pct=pct("salt_pct", 0.025, 0, 10),
        yeast_pct=0.0,
        oil_pct=pct("oil_pct", 0.0, 0, 20),
        sugar_pct=pct("sugar_pct", 0.0, 0, 20),
        preferment_pct=pct("preferment_pct", 0.0, 0, 100),
        preferment_hydration_pct=pct("preferment_hydration_pct", 1.0, 30, 150),
    )


def _baking_advice(preset: Preset, oven_profile: str) -> dict[str, Any]:
    if oven_profile == "split":
        return {
            "oven_profile": oven_profile,
            "mode": "Forno elettrico con cielo e platea indipendenti",
            "preheat_minutes": preset.baking.preheat_minutes,
            "plate_c": preset.baking.split_plate_c,
            "ceiling_c": preset.baking.split_ceiling_c,
            "bake_minutes": preset.baking.split_minutes,
            "position": "Pietra",
            "note": preset.baking.split_hint,
        }
    return {
        "oven_profile": oven_profile,
        "mode": preset.baking.mode,
        "preheat_c": preset.baking.preheat_c,
        "preheat_minutes": preset.baking.preheat_minutes,
        "bake_c": preset.baking.bake_c,
        "bake_minutes": preset.baking.bake_minutes,
        "position": preset.baking.position,
        "note": preset.baking.note,
    }


def _default_recipe_ctx() -> dict[str, Any]:
    """Dati per prima apertura: usa il primo preset come default."""
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    start_default = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    p = PRESETS[0]
    return {
        "start_at": start_default,
        "initial_dough_c": 24.0,
        "recipe_name": p.label,
        "style": p.style.value,
        "preset_description": p.description,
        "flour_hint": p.flour_hint,
        "yeast_kind": p.yeast_kind.value,
        "oven_profile": "split",
        "target_work": p.target_work,
        "ingredients": asdict(p.ingredients),
        "baking": asdict(p.baking),
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


def _preset_ctx(
    key: str,
    yeast_kind: YeastKind | None = None,
    oven_profile: str = "split",
) -> dict[str, Any] | None:
    if oven_profile == "nettuno":
        oven_profile = "split"
    p = PRESETS_BY_KEY.get(key)
    if p is None:
        return None
    ctx = _default_recipe_ctx()
    ctx.update(
        recipe_name=p.label,
        style=p.style.value,
        preset_description=p.description,
        flour_hint=p.flour_hint,
        yeast_kind=(yeast_kind or p.yeast_kind).value,
        oven_profile=oven_profile,
        target_work=p.target_work,
        ingredients=asdict(p.ingredients),
        baking=asdict(p.baking),
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


def _compute_plan_and_ingredients(data: dict[str, str]) -> dict[str, Any]:
    """Dalla form al pacchetto completo (plan + ingredienti + dati form)."""
    try:
        start_at = datetime.fromisoformat(data.get("start_at") or "").replace(tzinfo=None)
    except ValueError:
        start_at = datetime.now().replace(second=0, microsecond=0)
    initial_c = _number(data, "initial_dough_c", 24, 0, 40)
    try:
        yeast_kind = YeastKind(data.get("yeast_kind") or YeastKind.FRESH.value)
    except ValueError:
        yeast_kind = YeastKind.FRESH
    target_work = _number(data, "target_work", DEFAULT_TARGET_WORK, 0.01, 100)
    ingredients = _parse_ingredients(data)
    preset_key = data.get("preset_key", "")
    preset = PRESETS_BY_KEY.get(preset_key, PRESETS[0])
    oven_profile = data.get("oven_profile", "split")
    if oven_profile == "nettuno":
        oven_profile = "split"
    if oven_profile not in {"home", "split"}:
        oven_profile = "split"

    baking = _baking_advice(preset, oven_profile)

    phases = _parse_phase_form(data)
    if not phases:
        phases = [PlanPhase(kind=PhaseKind.MIX, label="Impasto", hours=0.5, ambient_c=22,
                            container=Container.MASS_BOWL, environment=Environment.AMBIENT)]

    plan_input = PlanInput(
        start_at=start_at,
        initial_dough_c=initial_c,
        phases=phases,
        yeast_kind=yeast_kind,
        yeast_pct=0.0,
        target_work=target_work,
    )
    thermal_plan = build_plan(plan_input)
    active_mask = fermentation_activity_mask(thermal_plan.thermal, phases)
    suggested_pct = suggest_yeast_pct(
        thermal_plan.thermal,
        yeast_kind,
        target_work,
        active_mask=active_mask,
    )
    ingredients.yeast_pct = suggested_pct
    plan_input.yeast_pct = suggested_pct
    plan = build_plan(plan_input)
    weights = compute(ingredients)
    bake_snapshot = {
        "recipe_name": data.get("recipe_name") or data.get("preset_key") or "Ricetta personale",
        "preset_key": data.get("preset_key", ""),
        "started_at": start_at.isoformat(),
        "predicted_ready_at": plan.ready_at.isoformat() if plan.ready_at else None,
        "scheduled_end_at": plan.end_at.isoformat(),
        "initial_dough_c": initial_c,
        "yeast_kind": yeast_kind.value,
        "yeast_pct": suggested_pct,
        "ingredients": asdict(weights),
        "hydration_pct": ingredients.hydration_pct,
        "salt_pct": ingredients.salt_pct,
        "baking": baking,
        "baking_options": {p: _baking_advice(preset, p) for p in ("split", "home")},
        "phases": [
            {
                "kind": phase.phase.kind.value,
                "label": phase.phase.label,
                "start_at": phase.start_at.isoformat(),
                "end_at": phase.end_at.isoformat(),
                "hours": phase.phase.hours,
                "ambient_c": phase.phase.ambient_c,
            }
            for phase in plan.phases
        ],
    }

    return {
        "plan": plan,
        "weights": weights,
        "ingredients": ingredients,
        "suggested_pct": suggested_pct,
        "yeast_label": YEAST_PARAMS[yeast_kind].label,
        "yeast_kind": yeast_kind.value,
        "baking": baking,
        "bake_snapshot": bake_snapshot,
    }


def _make_bake_record(data: dict[str, str]) -> tuple[Bake, float | None, dict[str, Any]]:
    if len(data["snapshot_json"]) > 100_000:
        raise ValueError("Lo snapshot del piano è troppo grande")
    snapshot = json.loads(data["snapshot_json"])
    if not isinstance(snapshot, dict):
        raise ValueError("Lo snapshot del piano non è valido")

    started_at = datetime.fromisoformat(snapshot["started_at"])
    actual_ready_at = datetime.fromisoformat(data["actual_ready_at"])
    if actual_ready_at < started_at:
        raise ValueError("L'orario di maturità non può precedere l'impasto")

    predicted_value = snapshot.get("predicted_ready_at")
    predicted_ready_at = datetime.fromisoformat(predicted_value) if predicted_value else None
    delta_hours = (
        (actual_ready_at - predicted_ready_at).total_seconds() / 3600
        if predicted_ready_at
        else None
    )

    rating_value = data.get("rating", "").strip()
    rating = int(rating_value) if rating_value else None
    if rating is not None and rating not in range(1, 6):
        raise ValueError("Il voto deve essere compreso tra 1 e 5")

    temperature_value = data.get("observed_dough_c", "").strip()
    observed_dough_c = float(temperature_value) if temperature_value else None
    if observed_dough_c is not None and not 0 <= observed_dough_c <= 40:
        raise ValueError("La temperatura osservata deve essere tra 0 e 40 °C")

    actual_oven_profile = data.get("actual_oven_profile", "").strip()
    if actual_oven_profile and actual_oven_profile not in {"home", "split"}:
        raise ValueError("Il tipo di forno non è valido")
    actual_baking: dict[str, Any] = (
        {"oven_profile": actual_oven_profile} if actual_oven_profile else {}
    )

    def actual_baking_number(key: str, label: str, minimum: float, maximum: float) -> float | None:
        raw = data.get(key, "").strip()
        if not raw:
            return None
        try:
            value = float(raw)
        except ValueError as error:
            raise ValueError(f"{label}: inserisci un numero valido") from error
        if not minimum <= value <= maximum:
            raise ValueError(f"{label}: valore fuori intervallo")
        actual_baking[key.removeprefix("actual_")] = value
        return value

    actual_baking_number("actual_preheat_minutes", "Preriscaldamento", 0, 180)
    actual_baking_number("actual_preheat_c", "Temperatura di preriscaldamento", 100, 300)
    actual_baking_number("actual_bake_c", "Temperatura forno", 100, 300)
    actual_baking_number("actual_plate_c", "Temperatura platea", 100, 510)
    actual_baking_number("actual_ceiling_c", "Temperatura cielo", 100, 510)
    actual_baking_number("actual_bake_minutes", "Durata cottura", 0.5, 180)
    actual_position = data.get("actual_bake_position", "").strip()[:100]
    if actual_position:
        actual_baking["bake_position"] = actual_position
    if not any(key != "oven_profile" for key in actual_baking):
        actual_baking = {}

    record = Bake(
        started_at=started_at,
        notes=data.get("notes", "").strip()[:2000],
        rating=rating,
        log=[
            {"kind": "plan", "snapshot": snapshot},
            {
                "kind": "observation",
                "actual_ready_at": actual_ready_at.isoformat(),
                "observed_dough_c": observed_dough_c,
                "baking": actual_baking or None,
                "observed_at": datetime.now().isoformat(timespec="minutes"),
            },
        ],
    )
    return record, delta_hours, snapshot


def _bake_history_item(record: Bake) -> dict[str, Any]:
    entries = record.log if isinstance(record.log, list) else []
    plan_entry: dict[str, Any] = next((i for i in entries if i.get("kind") == "plan"), {})
    observation: dict[str, Any] = next((i for i in entries if i.get("kind") == "observation"), {})
    snapshot = plan_entry.get("snapshot", {})
    predicted_value = snapshot.get("predicted_ready_at")
    actual_value = observation.get("actual_ready_at")
    predicted = datetime.fromisoformat(predicted_value) if predicted_value else None
    actual = datetime.fromisoformat(actual_value) if actual_value else None
    delta_hours = (
        (actual - predicted).total_seconds() / 3600
        if actual and predicted
        else None
    )
    yeast_kind = YeastKind(snapshot.get("yeast_kind", YeastKind.FRESH.value))

    return {
        "recipe_name": snapshot.get("recipe_name", "Impasto"),
        "started_at": record.started_at,
        "predicted_ready_at": predicted,
        "actual_ready_at": actual,
        "delta_hours": delta_hours,
        "yeast_label": YEAST_PARAMS[yeast_kind].label,
        "yeast_pct": snapshot.get("yeast_pct"),
        "observed_dough_c": observation.get("observed_dough_c"),
        "baking": observation.get("baking"),
        "rating": record.rating,
        "notes": record.notes,
    }


async def _recent_bakes(limit: int = 12) -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        records = await session.scalars(
            select(Bake).order_by(Bake.started_at.desc(), Bake.id.desc()).limit(limit)
        )
        return [_bake_history_item(record) for record in records]


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
    ctx = _common_ctx()
    recipe = _preset_ctx(preset_key, yeast_kind, selected_oven) if preset_key else _default_recipe_ctx()
    if recipe is None:
        recipe = _default_recipe_ctx()
    ctx.update(recipe=recipe, bake_history=await _recent_bakes())
    return templates.TemplateResponse(request, "planner.html", ctx)


@app.post("/plan", response_class=HTMLResponse)
async def compute_plan(request: Request) -> HTMLResponse:
    form = await request.form()
    data = {k: str(v) for k, v in form.items()}
    bundle = _compute_plan_and_ingredients(data)
    ctx = _common_ctx()
    ctx.update(bundle, bake_history=await _recent_bakes(), bake_oob=True)
    return templates.TemplateResponse(request, "partials/plan_result.html", ctx)


@app.post("/bakes", response_class=HTMLResponse)
async def save_bake(request: Request) -> HTMLResponse:
    form = await request.form()
    data = {k: str(v) for k, v in form.items()}
    try:
        record, delta_hours, snapshot = _make_bake_record(data)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        try:
            snapshot = json.loads(data.get("snapshot_json", "{}")[:100_000])
        except json.JSONDecodeError:
            snapshot = {}
        if not isinstance(snapshot, dict):
            snapshot = {}
        ctx = _common_ctx()
        ctx.update(
            bake_snapshot=snapshot,
            bake_history=await _recent_bakes(),
            bake_error=str(error),
            bake_saved=False,
            bake_oob=False,
        )
        return templates.TemplateResponse(request, "partials/bake_history.html", ctx)

    async with SessionLocal() as session:
        session.add(record)
        await session.commit()

    ctx = _common_ctx()
    ctx.update(
        bake_snapshot=snapshot,
        bake_history=await _recent_bakes(),
        bake_saved=True,
        saved_delta_hours=delta_hours,
        bake_error=None,
        bake_oob=False,
    )
    return templates.TemplateResponse(request, "partials/bake_history.html", ctx)


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
