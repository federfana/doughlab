"""Dal form del pianificatore al piano: lettura difensiva dei campi, preset e calcolo."""
from __future__ import annotations

import math
from contextlib import suppress
from dataclasses import asdict
from datetime import datetime
from typing import Any

from .services.fermentation import (
    DEFAULT_TARGET_WORK,
    YEAST_PARAMS,
    YeastKind,
    suggest_yeast_pct,
)
from .services.ingredients import RecipeIngredients, compute
from .services.presets import PRESETS, PRESETS_BY_KEY, Preset
from .services.scheduler import (
    PhaseKind,
    PlanInput,
    PlanPhase,
    build_plan,
    fermentation_activity_mask,
)
from .services.thermal import Container, Environment, parse_container, parse_environment

# Gli stessi limiti degli input HTML: il server non si fida del client.
MAX_PHASES = 30


def number(data: dict[str, str], key: str, default: float, low: float, high: float) -> float:
    """Numero finito dentro [low, high]; valori assenti, illeggibili o NaN/inf danno `default`."""
    try:
        value = float(data.get(key) or default)
    except ValueError:
        return default
    return min(high, max(low, value)) if math.isfinite(value) else default


def parse_phase_form(data: dict[str, str]) -> list[PlanPhase]:
    """Legge campi index-based (phase_kind_0, phase_hours_0, ...)."""
    phases: list[PlanPhase] = []
    i = 0
    while f"phase_kind_{i}" in data and i < MAX_PHASES:
        with suppress(ValueError, KeyError):
            phases.append(
                PlanPhase(
                    kind=PhaseKind(data[f"phase_kind_{i}"]),
                    label=(data[f"phase_label_{i}"] or data[f"phase_kind_{i}"])[:80],
                    hours=number(data, f"phase_hours_{i}", 0, 0, 720),
                    ambient_c=number(data, f"phase_ambient_{i}", 22, -5, 50),
                    container=parse_container(data[f"phase_container_{i}"]),
                    environment=parse_environment(data[f"phase_env_{i}"]),
                )
            )
        i += 1
    return phases


def parse_ingredients(data: dict[str, str]) -> RecipeIngredients:
    def pct(key: str, default_fraction: float, low: float, high: float) -> float:
        # L'interfaccia usa percentuali umane (es. 62, 2.8, 0.15), qui convertiamo in frazione.
        return number(data, key, default_fraction * 100.0, low, high) / 100.0

    return RecipeIngredients(
        panetto_g=number(data, "panetto_g", 250, 30, 2000),
        n_panetti=int(number(data, "n_panetti", 4, 1, 200)),
        hydration_pct=pct("hydration_pct", 0.60, 40, 120),
        salt_pct=pct("salt_pct", 0.025, 0, 10),
        yeast_pct=0.0,
        oil_pct=pct("oil_pct", 0.0, 0, 20),
        sugar_pct=pct("sugar_pct", 0.0, 0, 20),
        preferment_pct=pct("preferment_pct", 0.0, 0, 100),
        preferment_hydration_pct=pct("preferment_hydration_pct", 1.0, 30, 150),
        preferment_yeast_share=pct("preferment_yeast_pct", 1.0, 0, 100),
    )


def baking_advice(preset: Preset, oven_profile: str) -> dict[str, Any]:
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


def default_recipe_ctx() -> dict[str, Any]:
    """Dati per prima apertura: usa il primo preset come default."""
    start_default = datetime.now().replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
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


def preset_ctx(
    key: str,
    yeast_kind: YeastKind | None = None,
    oven_profile: str = "split",
) -> dict[str, Any] | None:
    if oven_profile == "nettuno":
        oven_profile = "split"
    p = PRESETS_BY_KEY.get(key)
    if p is None:
        return None
    ctx = default_recipe_ctx()
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


def compute_plan_and_ingredients(data: dict[str, str]) -> dict[str, Any]:
    """Dalla form al pacchetto completo (plan + ingredienti + dati form)."""
    try:
        start_at = datetime.fromisoformat(data.get("start_at") or "").replace(tzinfo=None)
    except ValueError:
        start_at = datetime.now().replace(second=0, microsecond=0)
    initial_c = number(data, "initial_dough_c", 24, 0, 40)
    try:
        yeast_kind = YeastKind(data.get("yeast_kind") or YeastKind.FRESH.value)
    except ValueError:
        yeast_kind = YeastKind.FRESH
    target_work = number(data, "target_work", DEFAULT_TARGET_WORK, 0.01, 100)
    ingredients = parse_ingredients(data)
    preset_key = data.get("preset_key", "")
    preset = PRESETS_BY_KEY.get(preset_key, PRESETS[0])
    oven_profile = data.get("oven_profile", "split")
    if oven_profile == "nettuno":
        oven_profile = "split"
    if oven_profile not in {"home", "split"}:
        oven_profile = "split"

    baking = baking_advice(preset, oven_profile)

    phases = parse_phase_form(data)
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
    plan_snapshot = {
        "recipe_name": data.get("recipe_name") or data.get("preset_key") or "Ricetta personale",
        "preset_key": data.get("preset_key", ""),
        "recipe_id": int(number(data, "recipe_id", 0, 0, 1e9)) or None,
        "recipe_version": int(number(data, "recipe_version", 0, 0, 1e9)) or None,
        "started_at": start_at.isoformat(),
        "predicted_ready_at": plan.ready_at.isoformat() if plan.ready_at else None,
        "scheduled_end_at": plan.end_at.isoformat(),
        "initial_dough_c": initial_c,
        "yeast_kind": yeast_kind.value,
        "yeast_pct": suggested_pct,
        "panetto_g": ingredients.panetto_g,
        "n_panetti": ingredients.n_panetti,
        "ingredients": asdict(weights),
        "hydration_pct": ingredients.hydration_pct,
        "salt_pct": ingredients.salt_pct,
        "preferment_pct": ingredients.preferment_pct,
        "baking": baking,
        "phases": [
            {
                "kind": phase.phase.kind.value,
                "label": phase.phase.label,
                "environment": phase.phase.environment.value,
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
        "plan_snapshot": plan_snapshot,
    }
