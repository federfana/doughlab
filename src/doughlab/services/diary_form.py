"""Modulo del Diario: valori dei campi, precompilazione da un piano, lettura del form e vista di una prova.

Solo logica senza accesso al database né a FastAPI: la usano le rotte di `diary.py` e si prova da sola.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from ..models import DiaryEntry
from .backup import (
    FLOAT_FIELDS,
    KNEADING_LABELS,
    MAX_PLAN_BYTES,
    TEXT_FIELDS,
    parse_rating,
)
from .fields import (
    clean_text,
    format_hours,
    format_minutes,
    format_number,
    parse_date,
    parse_datetime,
    parse_float,
    parse_int,
)
from .presets import PRESETS_BY_KEY

SLOT_LABELS = (
    ("main", "Principale"),
    ("extra1", "Extra 1"),
    ("extra2", "Extra 2"),
    ("extra3", "Extra 3"),
    ("extra4", "Extra 4"),
)

TEXT_COLUMNS = {column: limit for column, limit in TEXT_FIELDS.values()}

FLOAT_COLUMNS = {column: (low, high) for column, low, high in FLOAT_FIELDS.values()}

ALL_COLUMNS = (
    *TEXT_COLUMNS,
    *FLOAT_COLUMNS,
    "dough_ball_count",
    "rating",
    "kneading",
    "date",
    "plan",
    "started_at",
    "ready_at",
)

OVEN_LABELS = {"home": "Forno di casa", "split": "Forno elettrico (cielo e platea)"}

ROOM_PHASES = {"preferment", "bulk", "fold", "maturation", "temper", "proof"}

DATETIME_LOCAL = "%Y-%m-%dT%H:%M"


def blank_values() -> dict[str, str]:
    values = dict.fromkeys((*TEXT_COLUMNS, *FLOAT_COLUMNS), "")
    values.update(dough_ball_count="", rating="", kneading="", started_at="", ready_at="")
    values["date"] = date.today().isoformat()
    return values


def new_form(values: dict[str, str] | None = None, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "entry_id": None,
        "data": values or blank_values(),
        "plan": plan,
        "photos": [],
        "error": None,
    }


def photo_infos(entry: DiaryEntry) -> list[dict[str, Any]]:
    labels = dict(SLOT_LABELS)
    return [
        {
            "id": p.id,
            "slot": p.slot,
            "slot_label": labels.get(p.slot, p.slot),
            "label": p.label,
            "version": int(entry.updated_at.timestamp()),
        }
        for p in entry.photos
    ]


def values_from_entry(entry: DiaryEntry) -> dict[str, str]:
    values = blank_values()
    for column in TEXT_COLUMNS:
        values[column] = getattr(entry, column) or ""
    for column in (*FLOAT_COLUMNS, "dough_ball_count", "rating"):
        values[column] = format_number(getattr(entry, column))
    values["date"] = entry.date.isoformat()
    values["kneading"] = entry.kneading
    for column in ("started_at", "ready_at"):
        moment: datetime | None = getattr(entry, column)
        values[column] = moment.strftime(DATETIME_LOCAL) if moment else ""
    return values


def form_from_entry(entry: DiaryEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.id,
        "data": values_from_entry(entry),
        "plan": entry.plan,
        "photos": photo_infos(entry),
        "error": None,
    }


def hours(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def flour_component_lines(flours: Any, total_g: float) -> list[str]:
    """Una riga per farina (peso e percentuale) quando la miscela ne ha più di una."""
    if not isinstance(flours, list) or len(flours) < 2:
        return []
    lines: list[str] = []
    for item in flours:
        if not isinstance(item, dict):
            continue
        pct = hours(item.get("pct"))
        label = " ".join(str(item.get(key) or "") for key in ("brand", "name")).strip() or "Farina"
        lines.append(f"  · {label} {total_g * pct / 100:.0f} g ({pct:g}%)")
    return lines


def form_from_plan(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Modulo nuovo precompilato con quanto previsto dal piano (tutto resta modificabile)."""
    values = blank_values()
    weights: dict[str, Any] = snapshot.get("ingredients") or {}
    baking: dict[str, Any] = snapshot.get("baking") or {}
    phases: list[dict[str, Any]] = snapshot.get("phases") or []
    preset = PRESETS_BY_KEY.get(str(snapshot.get("preset_key", "")))
    started = parse_datetime(snapshot.get("started_at"))

    values["name"] = clean_text(snapshot.get("recipe_name"), 120)
    if snapshot.get("kneading") in KNEADING_LABELS:
        values["kneading"] = snapshot["kneading"]
    values["pizza_type"] = preset.label[:60] if preset else ""
    if snapshot.get("flour_label"):
        values["flour"] = clean_text(snapshot["flour_label"], TEXT_COLUMNS["flour"])
        values["flour_w"] = format_number(snapshot.get("flour_w"))
        values["protein"] = format_number(snapshot.get("flour_protein"))
    if started:
        values["date"] = started.date().isoformat()
        values["started_at"] = started.strftime(DATETIME_LOCAL)
    values["hydration"] = format_number(round(hours(snapshot.get("hydration_pct")) * 100, 1))
    values["dough_ball_weight"] = format_number(snapshot.get("panetto_g"))
    values["dough_ball_count"] = format_number(snapshot.get("n_panetti"))
    if hours(snapshot.get("preferment_pct")) > 0:
        values["preferment"] = f"{hours(snapshot['preferment_pct']) * 100:g}%"

    cold = sum(hours(p.get("hours")) for p in phases if str(p.get("environment")).startswith("fridge"))
    room = sum(
        hours(p.get("hours"))
        for p in phases
        if p.get("kind") in ROOM_PHASES and not str(p.get("environment")).startswith("fridge")
    )
    values["cold_hours"] = format_number(round(cold, 1)) if cold else ""
    values["room_hours"] = format_number(round(room, 1)) if room else ""

    profile = baking.get("oven_profile")
    values["oven"] = OVEN_LABELS.get(str(profile), "")
    if profile == "split":
        values["bake_temp"] = format_number(baking.get("plate_c"))
        values["bake_setup"] = f"Platea {baking.get('plate_c')} °C, cielo {baking.get('ceiling_c')} °C"
    else:
        values["bake_temp"] = format_number(baking.get("bake_c"))
        values["bake_setup"] = clean_text(baking.get("position"), 200)
    if baking.get("bake_minutes") is not None:
        values["bake_time"] = format_minutes(float(baking["bake_minutes"]))

    water_c = snapshot.get("water_c")
    water_note = f" a {water_c:.1f} °C".replace(".", ",") if isinstance(water_c, (int, float)) else ""
    lines = [
        f"Farina {hours(weights.get('flour_g')):.0f} g",
        *flour_component_lines(snapshot.get("flours"), hours(weights.get("flour_g"))),
        f"Acqua {hours(weights.get('water_g')):.0f} g{water_note}",
        f"Sale {hours(weights.get('salt_g')):.1f} g",
        f"Lievito {hours(weights.get('yeast_g')):.2f} g",
    ]
    if hours(weights.get("oil_g")) > 0:
        lines.append(f"Olio {hours(weights['oil_g']):.1f} g")
    if hours(weights.get("sugar_g")) > 0:
        lines.append(f"Zucchero {hours(weights['sugar_g']):.1f} g")
    if hours(weights.get("preferment_flour_g")) > 0:
        lines.append(
            f"Prefermento: farina {hours(weights['preferment_flour_g']):.0f} g, "
            f"acqua {hours(weights.get('preferment_water_g')):.0f} g, "
            f"lievito {hours(weights.get('preferment_yeast_g')):.2f} g"
        )
    values["ingredients"] = "\n".join(lines)

    steps: list[str] = []
    for phase in phases:
        begin, end = parse_datetime(phase.get("start_at")), parse_datetime(phase.get("end_at"))
        end_fmt = "%H:%M" if begin and end and begin.date() == end.date() else "%d/%m %H:%M"
        when = f" ({begin:%d/%m %H:%M} - {end.strftime(end_fmt)})" if begin and end else ""
        steps.append(f"{phase.get('label', '')}: {format_hours(hours(phase.get('hours')))}{when}")
    values["process"] = "\n".join(steps)
    return new_form(values, snapshot)


def parse_fields(data: dict[str, str]) -> tuple[dict[str, Any], str | None]:
    """Valori del modulo come colonne; il secondo elemento è il messaggio d'errore, se c'è."""
    fields: dict[str, Any] = {}
    for column, limit in TEXT_COLUMNS.items():
        fields[column] = clean_text(data.get(column), limit)
    for column, (low, high) in FLOAT_COLUMNS.items():
        fields[column] = parse_float(data.get(column), low, high)
    fields["dough_ball_count"] = parse_int(data.get("dough_ball_count"), 0, 1_000)
    fields["rating"] = parse_rating(data.get("rating"))
    kneading = data.get("kneading", "")
    fields["kneading"] = kneading if kneading in KNEADING_LABELS else ""
    if not fields["name"]:
        return fields, "Dai un nome alla prova."
    day = parse_date(data.get("date"))
    if day is None:
        return fields, "La data non è valida."
    fields["date"] = day
    started, ready = parse_datetime(data.get("started_at")), parse_datetime(data.get("ready_at"))
    if started and ready and ready < started:
        return fields, "L'impasto non può essere pronto prima di iniziare: controlla gli orari."
    fields["started_at"], fields["ready_at"] = started, ready
    return fields, None


def plan_from_form(data: dict[str, str]) -> dict[str, Any] | None:
    raw = data.get("plan_json", "")
    if not raw or len(raw) > MAX_PLAN_BYTES:
        return None
    try:
        plan = json.loads(raw)
    except ValueError:
        return None
    return plan if isinstance(plan, dict) else None


def recipe_label(plan: dict[str, Any]) -> str:
    if not isinstance(plan.get("recipe_id"), int):
        return ""
    version = plan.get("recipe_version")
    suffix = f" v{version}" if isinstance(version, int) else ""
    return f"{clean_text(plan.get('recipe_name'), 80)}{suffix}"


def entry_matches(entry: DiaryEntry, query: str) -> bool:
    haystack = " ".join(
        (entry.name, entry.pizza_type, entry.tags, entry.notes, entry.flour, entry.oven, entry.next_changes)
    )
    return all(word in haystack.lower() for word in query.lower().split())


def entry_view(entry: DiaryEntry) -> dict[str, Any]:
    plan = entry.plan or {}
    predicted = parse_datetime(plan.get("predicted_ready_at"))
    plan_start = parse_datetime(plan.get("started_at"))
    ready, started = entry.ready_at, entry.started_at
    duration = (ready - started).total_seconds() / 3600 if ready and started else None
    predicted_hours = (predicted - plan_start).total_seconds() / 3600 if predicted and plan_start else None
    if duration is not None and predicted_hours is not None:
        delta: float | None = duration - predicted_hours
    elif ready and predicted:
        delta = (ready - predicted).total_seconds() / 3600  # piani vecchi senza partenza
    else:
        delta = None
    chips: list[str] = []
    if entry.hydration is not None:
        chips.append(f"idratazione {format_number(entry.hydration)}%")
    if entry.cold_hours:
        chips.append(f"{format_hours(entry.cold_hours)} in frigo")
    if entry.room_hours:
        chips.append(f"{format_hours(entry.room_hours)} a temp. ambiente")
    if entry.dough_ball_count and entry.dough_ball_weight:
        chips.append(f"{entry.dough_ball_count} × {format_number(entry.dough_ball_weight)} g")
    if entry.kneading in KNEADING_LABELS:
        chips.append(f"impastato: {KNEADING_LABELS[entry.kneading].lower()}")
    if entry.bake_temp is not None:
        chips.append(f"{format_number(entry.bake_temp)} °C")
    if entry.bake_time:
        chips.append(entry.bake_time)
    photos = [
        {"id": p.id, "label": p.label, "slot": p.slot} for p in entry.photos
    ]
    return {
        "id": entry.id,
        "name": entry.name,
        "date": entry.date,
        "pizza_type": entry.pizza_type,
        "oven": entry.oven,
        "rating": format_number(entry.rating).replace(".", ","),
        "rating_pct": round(entry.rating / 5 * 100) if entry.rating else None,
        "chips": chips,
        "photos": photos,
        "cover_id": next(
            (p["id"] for p in photos if p["slot"] == "main"), photos[0]["id"] if photos else None
        ),
        "version": int(entry.updated_at.timestamp()),
        "entry": entry,
        "recipe_id": plan.get("recipe_id") if isinstance(plan.get("recipe_id"), int) else None,
        "recipe_label": recipe_label(plan),
        "recipe_name": clean_text(plan.get("recipe_name"), 80),
        "started_at": started,
        "ready_at": ready,
        "predicted_ready_at": predicted,
        "plan_start": plan_start,
        "predicted_hours": predicted_hours,
        "delta_hours": delta,
        "duration_hours": duration,
    }


def entry_view_recipe(entry: DiaryEntry) -> int | None:
    value = (entry.plan or {}).get("recipe_id")
    return value if isinstance(value, int) else None
