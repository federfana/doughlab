"""Dal form del pianificatore al piano: lettura difensiva dei campi, preset e calcolo."""
from __future__ import annotations

import math
from contextlib import suppress
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

from .services.fermentation import (
    DEFAULT_TARGET_WORK,
    YEAST_PARAMS,
    YeastKind,
    program_length_factor,
    suggest_yeast_pct,
)
from .services.ingredients import RecipeIngredients, compute
from .services.presets import PRESETS, PRESETS_BY_KEY, Preset
from .services.scheduler import (
    FERMENTING_PHASES,
    PhaseKind,
    PlanInput,
    PlanPhase,
    build_plan,
    fermentation_activity_mask,
)
from .services.strategies import (
    BIGA_HOURS,
    FOLD_KNEADING,
    OPEN_HOURS,
    POOLISH_HOURS,
    build_phases,
    with_folds,
)
from .services.thermal import Container, Environment, parse_container, parse_environment
from .services.water import DEFAULT_FLOUR_C, DEFAULT_KNEADING, FRICTION_C, water_temperature

# Gli stessi limiti degli input HTML: il server non si fida del client.
MAX_PHASES = 30


def number(data: dict[str, str], key: str, default: float, low: float, high: float) -> float:
    """Numero finito dentro [low, high]; valori assenti, illeggibili o NaN/inf danno `default`."""
    try:
        value = float(data.get(key) or default)
    except ValueError:
        return default
    return min(high, max(low, value)) if math.isfinite(value) else default


_MATURATION_LABELS = {
    Environment.FRIDGE_HOME: "Maturazione in frigo",
    Environment.CHAMBER: "Maturazione in cella",
    Environment.AMBIENT: "Maturazione a temperatura ambiente",
}


def phase_label(kind: PhaseKind, label: str, environment: Environment) -> str:
    """Il nome di una maturazione segue la sua condizione; i nomi scelti da te restano."""
    if kind == PhaseKind.MATURATION and (label in _MATURATION_LABELS.values() or label == "Maturazione"):
        return _MATURATION_LABELS.get(environment, label)
    return label


def parse_phase_form(data: dict[str, str]) -> list[PlanPhase]:
    """Legge campi index-based (phase_kind_0, phase_hours_0, ...)."""
    phases: list[PlanPhase] = []
    i = 0
    while f"phase_kind_{i}" in data and i < MAX_PHASES:
        with suppress(ValueError, KeyError):
            kind = PhaseKind(data[f"phase_kind_{i}"])
            environment = parse_environment(data[f"phase_env_{i}"])
            label = (data[f"phase_label_{i}"] or data[f"phase_kind_{i}"])[:80]
            phases.append(
                PlanPhase(
                    kind=kind,
                    label=phase_label(kind, label, environment),
                    hours=number(data, f"phase_hours_{i}", 0, 0, 720),
                    ambient_c=number(data, f"phase_ambient_{i}", 22, -5, 50),
                    container=parse_container(data[f"phase_container_{i}"]),
                    environment=environment,
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


def local_datetime(value: str | None) -> datetime | None:
    """Data e ora del campo `datetime-local` (senza fuso); None se assente o illeggibile."""
    try:
        return datetime.fromisoformat(value or "").replace(tzinfo=None)
    except ValueError:
        return None


def hours_before_bake(phases: list[PlanPhase]) -> float:
    """Ore dall'inizio fino all'infornata: tutte le fasi, o quelle prima di una eventuale fase di cottura."""
    total = 0.0
    for phase in phases:
        if phase.kind == PhaseKind.BAKE:
            break
        total += phase.hours
    return total


DEFAULT_ROOM_C = 22.0
DEFAULT_FRIDGE_C = 4.0


def phase_dicts(phases: list[PlanPhase]) -> list[dict[str, Any]]:
    return [
        {
            "kind": ph.kind.value, "label": ph.label, "hours": ph.hours,
            "ambient_c": ph.ambient_c, "container": ph.container.value,
            "environment": ph.environment.value,
        }
        for ph in phases
    ]


def guided_settings(preset: Preset | None = None) -> dict[str, Any]:
    """Valori iniziali della modalità guidata: strategia di lievitazione e temperature."""
    return {
        "mode": "guided",
        "mode_forced": False,
        "strategy": preset.strategy if preset else "fridge_24",
        "room_c": DEFAULT_ROOM_C,
        "fridge_c": DEFAULT_FRIDGE_C,
    }


def guided_phases(
    data: dict[str, str], ingredients: RecipeIngredients, preset: Preset
) -> list[PlanPhase]:
    """Fasi generate dalla strategia scelta (modalità guidata); le temperature restano dell'utente."""
    pref_hours, pref_label = 0.0, "Prefermento"
    if ingredients.preferment_pct > 0:
        biga = ingredients.preferment_hydration_pct <= 0.65
        pref_hours, pref_label = (BIGA_HOURS, "Biga") if biga else (POOLISH_HOURS, "Poolish")
    return build_phases(
        data.get("strategy", ""),
        number(data, "room_c", DEFAULT_ROOM_C, 5, 40),
        number(data, "fridge_c", DEFAULT_FRIDGE_C, 0, 12),
        preferment_hours=pref_hours,
        preferment_label=pref_label,
        open_hours=OPEN_HOURS.get(preset.style.value, 0.0),
        folds=data.get("kneading", DEFAULT_KNEADING) in FOLD_KNEADING,
    )


def generated_phase_dicts(data: dict[str, str]) -> list[dict[str, Any]]:
    """Fasi della strategia scelta, per mostrarle e modificarle passando a «Esperto»."""
    preset = PRESETS_BY_KEY.get(data.get("preset_key", ""), PRESETS[0])
    return phase_dicts(guided_phases(data, parse_ingredients(data), preset))


def folded_phase_dicts(data: dict[str, str]) -> list[dict[str, Any]]:
    """Le fasi attuali (modalità Esperto) con le pieghe aggiunte o tolte secondo come si impasta."""
    folds = data.get("kneading", DEFAULT_KNEADING) in FOLD_KNEADING
    return phase_dicts(with_folds(parse_phase_form(data), folds))


def default_recipe_ctx() -> dict[str, Any]:
    """Dati per prima apertura: usa il primo preset come default."""
    now = datetime.now().replace(second=0, microsecond=0)
    start_default = now.strftime("%Y-%m-%dT%H:%M")
    # Cena di domani: punto di partenza ragionevole per «voglio infornare alle…».
    bake_default = (now + timedelta(days=1)).replace(hour=20, minute=30).strftime("%Y-%m-%dT%H:%M")
    p = PRESETS[0]
    return {
        "start_at": start_default,
        "bake_at": bake_default,
        "flour_c": DEFAULT_FLOUR_C,
        "kneading": DEFAULT_KNEADING,
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
        "phases": phase_dicts(with_folds(list(p.phases), DEFAULT_KNEADING in FOLD_KNEADING)),
        "active_preset": p.key,
        **guided_settings(p),
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
        phases=phase_dicts(with_folds(list(p.phases), DEFAULT_KNEADING in FOLD_KNEADING)),
        active_preset=p.key,
        **guided_settings(p),
    )
    return ctx


def compute_plan_and_ingredients(data: dict[str, str]) -> dict[str, Any]:
    """Dalla form al pacchetto completo (plan + ingredienti + dati form)."""
    start_at = local_datetime(data.get("start_at")) or datetime.now().replace(second=0, microsecond=0)
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

    phases = guided_phases(data, ingredients, preset) if data.get("mode") == "guided" else parse_phase_form(data)
    if not phases:
        phases = [PlanPhase(kind=PhaseKind.MIX, label="Impasto", hours=0.5, ambient_c=22,
                            container=Container.MASS_BOWL, environment=Environment.AMBIENT)]

    run_hours = hours_before_bake(phases)
    bake_at = local_datetime(data.get("bake_at"))
    reverse = data.get("anchor") == "bake" and bake_at is not None
    if reverse and bake_at is not None:
        start_at = bake_at - timedelta(hours=run_hours)

    mix = next((p for p in phases if p.kind == PhaseKind.MIX), phases[0])
    kneading = data.get("kneading", "")
    if kneading not in FRICTION_C:
        kneading = DEFAULT_KNEADING
    flour_c = number(data, "flour_c", DEFAULT_FLOUR_C, 0, 40)
    preferment_phase = next((p for p in phases if p.kind == PhaseKind.PREFERMENT), None)
    preferment_c = None
    if ingredients.preferment_pct > 0:
        preferment_c = (preferment_phase or mix).ambient_c
    water = water_temperature(initial_c, mix.ambient_c, flour_c, kneading, preferment_c)

    plan_input = PlanInput(
        start_at=start_at,
        initial_dough_c=water.dough_c,
        phases=phases,
        yeast_kind=yeast_kind,
        yeast_pct=0.0,
        target_work=target_work,
    )
    # Il preimpasto matura con la sua dose: non conta come ore dell'impasto finale.
    dough_hours = sum(
        p.hours for p in phases if p.kind in FERMENTING_PHASES and p.kind != PhaseKind.PREFERMENT
    )
    target_work *= program_length_factor(dough_hours, yeast_kind)
    plan_input.target_work = target_work
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
        "initial_dough_c": water.dough_c,
        "flour_c": flour_c,
        "kneading": kneading,
        "water_c": water.temperature_c,
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
        "water": water,
        "anchor": "bake" if reverse else "start",
        "plan_start_at": start_at,
        "plan_oven_at": start_at + timedelta(hours=run_hours),
        "start_in_past": start_at < datetime.now(),
    }
