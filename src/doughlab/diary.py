"""Diario delle prove: elenco, modulo, foto, importazione ed esportazione dei backup."""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload, undefer
from starlette.datastructures import FormData, UploadFile

from .db import SessionLocal
from .models import DiaryEntry, DiaryPhoto, utcnow
from .services.backup import (
    FLOAT_FIELDS,
    MAX_PLAN_BYTES,
    TEXT_FIELDS,
    DiaryData,
    DiaryPhotoData,
    build_backup,
    parse_backup,
    parse_rating,
)
from .services.fields import (
    clean_text,
    format_number,
    parse_date,
    parse_datetime,
    parse_float,
    parse_int,
)
from .services.images import MAX_PHOTO_BYTES, SLOTS, sniff_image_mime
from .services.presets import PRESETS_BY_KEY
from .web import RowId, common_ctx, templates

router = APIRouter(prefix="/diario")

MAX_IMPORT_BYTES = 100_000_000
MAX_FORM_BYTES = (len(SLOTS) * MAX_PHOTO_BYTES) + 2_000_000
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
    "date",
    "plan",
    "started_at",
    "ready_at",
)
OVEN_LABELS = {"home": "Forno di casa", "split": "Forno elettrico (cielo e platea)"}
ROOM_PHASES = {"preferment", "bulk", "maturation", "temper", "proof"}
DATETIME_LOCAL = "%Y-%m-%dT%H:%M"


# --- Modulo -----------------------------------------------------------------------------------


def _blank_values() -> dict[str, str]:
    values = dict.fromkeys((*TEXT_COLUMNS, *FLOAT_COLUMNS), "")
    values.update(dough_ball_count="", rating="", started_at="", ready_at="")
    values["date"] = date.today().isoformat()
    return values


def _new_form(values: dict[str, str] | None = None, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "entry_id": None,
        "data": values or _blank_values(),
        "plan": plan,
        "photos": [],
        "error": None,
    }


def _photo_infos(entry: DiaryEntry) -> list[dict[str, Any]]:
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


def _values_from_entry(entry: DiaryEntry) -> dict[str, str]:
    values = _blank_values()
    for column in TEXT_COLUMNS:
        values[column] = getattr(entry, column) or ""
    for column in (*FLOAT_COLUMNS, "dough_ball_count", "rating"):
        values[column] = format_number(getattr(entry, column))
    values["date"] = entry.date.isoformat()
    for column in ("started_at", "ready_at"):
        moment: datetime | None = getattr(entry, column)
        values[column] = moment.strftime(DATETIME_LOCAL) if moment else ""
    return values


def _form_from_entry(entry: DiaryEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.id,
        "data": _values_from_entry(entry),
        "plan": entry.plan,
        "photos": _photo_infos(entry),
        "error": None,
    }


def _hours(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def form_from_plan(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Modulo nuovo precompilato con quanto previsto dal piano (tutto resta modificabile)."""
    values = _blank_values()
    weights: dict[str, Any] = snapshot.get("ingredients") or {}
    baking: dict[str, Any] = snapshot.get("baking") or {}
    phases: list[dict[str, Any]] = snapshot.get("phases") or []
    preset = PRESETS_BY_KEY.get(str(snapshot.get("preset_key", "")))
    started = parse_datetime(snapshot.get("started_at"))

    values["name"] = clean_text(snapshot.get("recipe_name"), 120)
    values["pizza_type"] = preset.label[:60] if preset else ""
    if started:
        values["date"] = started.date().isoformat()
        values["started_at"] = started.strftime(DATETIME_LOCAL)
    values["hydration"] = format_number(round(_hours(snapshot.get("hydration_pct")) * 100, 1))
    values["dough_ball_weight"] = format_number(snapshot.get("panetto_g"))
    values["dough_ball_count"] = format_number(snapshot.get("n_panetti"))
    if _hours(snapshot.get("preferment_pct")) > 0:
        values["preferment"] = f"{_hours(snapshot['preferment_pct']) * 100:g}%"

    cold = sum(_hours(p.get("hours")) for p in phases if str(p.get("environment")).startswith("fridge"))
    room = sum(
        _hours(p.get("hours"))
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
        values["bake_time"] = f"{format_number(baking.get('bake_minutes'))} min"

    lines = [
        f"Farina {_hours(weights.get('flour_g')):.0f} g",
        f"Acqua {_hours(weights.get('water_g')):.0f} g",
        f"Sale {_hours(weights.get('salt_g')):.1f} g",
        f"Lievito {_hours(weights.get('yeast_g')):.2f} g",
    ]
    if _hours(weights.get("oil_g")) > 0:
        lines.append(f"Olio {_hours(weights['oil_g']):.1f} g")
    if _hours(weights.get("sugar_g")) > 0:
        lines.append(f"Zucchero {_hours(weights['sugar_g']):.1f} g")
    if _hours(weights.get("preferment_flour_g")) > 0:
        lines.append(
            f"Prefermento: farina {_hours(weights['preferment_flour_g']):.0f} g, "
            f"acqua {_hours(weights.get('preferment_water_g')):.0f} g"
        )
    values["ingredients"] = "\n".join(lines)

    steps: list[str] = []
    for phase in phases:
        begin, end = parse_datetime(phase.get("start_at")), parse_datetime(phase.get("end_at"))
        when = f" ({begin:%d/%m %H:%M} - {end:%H:%M})" if begin and end else ""
        steps.append(f"{phase.get('label', '')}: {format_number(_hours(phase.get('hours')))} h{when}")
    values["process"] = "\n".join(steps)
    return _new_form(values, snapshot)


def _parse_fields(data: dict[str, str]) -> tuple[dict[str, Any], str | None]:
    """Valori del modulo come colonne; il secondo elemento è il messaggio d'errore, se c'è."""
    fields: dict[str, Any] = {}
    for column, limit in TEXT_COLUMNS.items():
        fields[column] = clean_text(data.get(column), limit)
    for column, (low, high) in FLOAT_COLUMNS.items():
        fields[column] = parse_float(data.get(column), low, high)
    fields["dough_ball_count"] = parse_int(data.get("dough_ball_count"), 0, 1_000)
    fields["rating"] = parse_rating(data.get("rating"))
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


def _plan_from_form(data: dict[str, str]) -> dict[str, Any] | None:
    raw = data.get("plan_json", "")
    if not raw or len(raw) > MAX_PLAN_BYTES:
        return None
    try:
        plan = json.loads(raw)
    except ValueError:
        return None
    return plan if isinstance(plan, dict) else None


async def _apply_photos(entry: DiaryEntry, form: FormData, data: dict[str, str]) -> str | None:
    existing = {photo.slot: photo for photo in entry.photos}
    for slot, slot_label in SLOT_LABELS:
        label = clean_text(data.get(f"label_{slot}"), 120)
        upload = form.get(f"photo_{slot}")
        if isinstance(upload, UploadFile) and upload.filename:
            raw = await upload.read(MAX_PHOTO_BYTES + 1)
            if len(raw) > MAX_PHOTO_BYTES:
                return f"La foto «{slot_label}» è troppo grande."
            if raw:
                mime = sniff_image_mime(raw)
                if mime is None:
                    return f"La foto «{slot_label}» deve essere JPEG, PNG o WebP."
                if slot in existing:
                    existing[slot].data, existing[slot].mime = raw, mime
                    existing[slot].label = label
                else:
                    entry.photos.append(DiaryPhoto(slot=slot, mime=mime, data=raw, label=label))
                continue
        if slot in existing:
            if data.get(f"remove_{slot}"):
                entry.photos.remove(existing[slot])
            else:
                existing[slot].label = label
    return None


def _too_large(request: Request, limit: int) -> bool:
    length = request.headers.get("content-length", "")
    return length.isdigit() and int(length) > limit


# --- Viste ------------------------------------------------------------------------------------


def _recipe_label(plan: dict[str, Any]) -> str:
    if not isinstance(plan.get("recipe_id"), int):
        return ""
    version = plan.get("recipe_version")
    suffix = f" v{version}" if isinstance(version, int) else ""
    return f"{clean_text(plan.get('recipe_name'), 80)}{suffix}"


def _matches(entry: DiaryEntry, query: str) -> bool:
    haystack = " ".join(
        (entry.name, entry.pizza_type, entry.tags, entry.notes, entry.flour, entry.oven, entry.next_changes)
    )
    return all(word in haystack.lower() for word in query.lower().split())


def _entry_view(entry: DiaryEntry) -> dict[str, Any]:
    plan = entry.plan or {}
    predicted = parse_datetime(plan.get("predicted_ready_at"))
    ready, started = entry.ready_at, entry.started_at
    chips: list[str] = []
    if entry.hydration is not None:
        chips.append(f"idratazione {format_number(entry.hydration)}%")
    if entry.cold_hours:
        chips.append(f"{format_number(entry.cold_hours)} h frigo")
    if entry.room_hours:
        chips.append(f"{format_number(entry.room_hours)} h ambiente")
    if entry.dough_ball_count and entry.dough_ball_weight:
        chips.append(f"{entry.dough_ball_count} × {format_number(entry.dough_ball_weight)} g")
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
        "chips": chips,
        "photos": photos,
        "cover_id": next(
            (p["id"] for p in photos if p["slot"] == "main"), photos[0]["id"] if photos else None
        ),
        "version": int(entry.updated_at.timestamp()),
        "entry": entry,
        "recipe_id": plan.get("recipe_id") if isinstance(plan.get("recipe_id"), int) else None,
        "recipe_label": _recipe_label(plan),
        "recipe_name": clean_text(plan.get("recipe_name"), 80),
        "started_at": started,
        "ready_at": ready,
        "predicted_ready_at": predicted,
        "delta_hours": (ready - predicted).total_seconds() / 3600 if ready and predicted else None,
        "duration_hours": (ready - started).total_seconds() / 3600 if ready and started else None,
    }


def _entry_view_recipe(entry: DiaryEntry) -> int | None:
    value = (entry.plan or {}).get("recipe_id")
    return value if isinstance(value, int) else None


async def panel_context(
    form: dict[str, Any] | None = None,
    message: str | None = None,
    report: dict[str, Any] | None = None,
    query: str = "",
    recipe_id: int | None = None,
) -> dict[str, Any]:
    async with SessionLocal() as session:
        entries = (
            await session.scalars(
                select(DiaryEntry).order_by(DiaryEntry.date.desc(), DiaryEntry.id.desc())
            )
        ).all()
    query = query.strip()[:100]
    total = len(entries)
    items = [
        _entry_view(entry)
        for entry in entries
        if (not query or _matches(entry, query))
        and (recipe_id is None or _entry_view_recipe(entry) == recipe_id)
    ]
    recipe_filter = next((i["recipe_name"] for i in items if recipe_id is not None), "")
    return {
        "diary_items": items,
        "diary_total": total,
        "diary_query": query,
        "diary_recipe": recipe_id,
        "diary_recipe_label": recipe_filter,
        "diary_form": form,
        "diary_message": message,
        "diary_report": report,
        "diary_slots": SLOT_LABELS,
    }


async def _panel(request: Request, **kwargs: Any) -> HTMLResponse:
    ctx = common_ctx()
    ctx.update(await panel_context(**kwargs))
    return templates.TemplateResponse(request, "partials/diary_panel.html", ctx)


async def _read_form(request: Request) -> tuple[FormData, dict[str, str]] | None:
    if _too_large(request, MAX_FORM_BYTES):
        return None
    form = await request.form()
    data = {k: v for k, v in form.items() if isinstance(v, str)}
    return form, data


# --- Rotte ------------------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
async def diary_list(
    request: Request, q: str = "", recipe: Annotated[int | None, Query(ge=1, le=2_147_483_647)] = None
) -> HTMLResponse:
    return await _panel(request, query=q, recipe_id=recipe)


@router.get("/nuova", response_class=HTMLResponse)
async def diary_new(request: Request) -> HTMLResponse:
    return await _panel(request, form=_new_form())


@router.get("/{entry_id:int}/modifica", response_class=HTMLResponse)
async def diary_edit(request: Request, entry_id: RowId) -> HTMLResponse:
    async with SessionLocal() as session:
        entry = await session.get(DiaryEntry, entry_id)
        form = _form_from_entry(entry) if entry else None
    if form is None:
        return await _panel(request, message="Voce non trovata.")
    return await _panel(request, form=form)


@router.post("", response_class=HTMLResponse)
async def diary_create(request: Request) -> HTMLResponse:
    parsed = await _read_form(request)
    if parsed is None:
        return await _panel(request, form=_new_form(), message="Le foto sono troppo grandi.")
    form, data = parsed
    fields, error = _parse_fields(data)
    plan = _plan_from_form(data)
    entry = DiaryEntry(external_id=str(uuid4()), extra={}, plan=plan)
    if error is None:
        for column, value in fields.items():
            setattr(entry, column, value)
        error = await _apply_photos(entry, form, data)
    if error is not None:
        failed = _new_form({k: data.get(k, "") for k in _blank_values()}, plan)
        failed["error"] = error
        return await _panel(request, form=failed)
    async with SessionLocal() as session:
        session.add(entry)
        await session.commit()
    return await _panel(request, message="Prova salvata nel diario.")


@router.post("/{entry_id:int}", response_class=HTMLResponse)
async def diary_update(request: Request, entry_id: RowId) -> HTMLResponse:
    parsed = await _read_form(request)
    async with SessionLocal() as session:
        entry = await session.get(DiaryEntry, entry_id)
        if entry is None:
            return await _panel(request, message="Voce non trovata.")
        if parsed is None:
            failed = _form_from_entry(entry)
            failed["error"] = "Le foto sono troppo grandi."
            return await _panel(request, form=failed)
        form, data = parsed
        photos = _photo_infos(entry)
        fields, error = _parse_fields(data)
        if error is None:
            for column, value in fields.items():
                setattr(entry, column, value)
            error = await _apply_photos(entry, form, data)
        if error is not None:
            failed = {
                "entry_id": entry_id,
                "data": {k: data.get(k, "") for k in _blank_values()},
                "plan": entry.plan,
                "photos": photos,
                "error": error,
            }
            await session.rollback()
            return await _panel(request, form=failed)
        entry.updated_at = utcnow()
        await session.commit()
    return await _panel(request, message="Modifiche salvate.")


@router.post("/{entry_id:int}/elimina", response_class=HTMLResponse)
async def diary_delete(request: Request, entry_id: RowId) -> HTMLResponse:
    async with SessionLocal() as session:
        entry = await session.get(DiaryEntry, entry_id)
        if entry is not None:
            await session.delete(entry)
            await session.commit()
    return await _panel(request, message="Voce eliminata.")


@router.get("/foto/{photo_id:int}")
async def diary_photo(photo_id: RowId) -> Response:
    async with SessionLocal() as session:
        photo = await session.scalar(
            select(DiaryPhoto).where(DiaryPhoto.id == photo_id).options(undefer(DiaryPhoto.data))
        )
        if photo is None:
            return Response(status_code=404)
        content, mime = photo.data, photo.mime
    return Response(
        content=content,
        media_type=mime,
        headers={"Cache-Control": "private, max-age=31536000", "X-Content-Type-Options": "nosniff"},
    )


# --- Backup -----------------------------------------------------------------------------------


def _fill_from_data(entry: DiaryEntry, data: DiaryData) -> None:
    for column, value in data.fields.items():
        setattr(entry, column, value)
    entry.extra = data.extra
    entry.updated_at = data.updated_at or utcnow()
    existing = {photo.slot: photo for photo in entry.photos}
    for photo in data.photos:
        current = existing.pop(photo.slot, None)
        if current is None:
            entry.photos.append(
                DiaryPhoto(
                    slot=photo.slot,
                    mime=photo.mime,
                    data=photo.data,
                    label=photo.label,
                    settings=photo.settings,
                )
            )
        else:
            current.mime, current.data = photo.mime, photo.data
            current.label, current.settings = photo.label, photo.settings
    for leftover in existing.values():
        entry.photos.remove(leftover)


@router.post("/importa", response_class=HTMLResponse)
async def diary_import(request: Request) -> HTMLResponse:
    if _too_large(request, MAX_IMPORT_BYTES):
        return await _panel(request, message="Il file è troppo grande (massimo 100 MB).")
    form = await request.form()
    upload = form.get("file")
    if not isinstance(upload, UploadFile) or not upload.filename:
        return await _panel(request, message="Scegli un file di backup da importare.")
    raw = await upload.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        return await _panel(request, message="Il file è troppo grande (massimo 100 MB).")
    try:
        result = parse_backup(raw)
    except ValueError as error:
        return await _panel(request, message=f"Importazione non riuscita: {error}.")

    created = updated = skipped = 0
    async with SessionLocal() as session:
        known = {e.external_id: e for e in await session.scalars(select(DiaryEntry))}
        for item in result.entries:
            current = known.get(item.external_id)
            if current is None:
                entry = DiaryEntry(external_id=item.external_id, extra={}, plan=None)
                _fill_from_data(entry, item)
                session.add(entry)
                known[item.external_id] = entry
                created += 1
            elif item.updated_at and item.updated_at > current.updated_at:
                _fill_from_data(current, item)
                updated += 1
            else:
                skipped += 1
        await session.commit()
    report = {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "warnings": result.warnings[:20],
    }
    return await _panel(request, report=report)


def _entry_data(entry: DiaryEntry) -> DiaryData:
    return DiaryData(
        external_id=entry.external_id,
        fields={column: getattr(entry, column) for column in ALL_COLUMNS},
        photos=[
            DiaryPhotoData(p.slot, p.mime, p.data, p.label, dict(p.settings or {}))
            for p in entry.photos
        ],
        updated_at=entry.updated_at,
        extra=entry.extra or {},
    )


@router.get("/export.json")
async def diary_export() -> Response:
    async with SessionLocal() as session:
        entries = await session.scalars(
            select(DiaryEntry)
            .options(selectinload(DiaryEntry.photos).undefer(DiaryPhoto.data))
            .order_by(DiaryEntry.date.desc(), DiaryEntry.id.desc())
        )
        payload = build_backup([_entry_data(entry) for entry in entries])
    filename = f"doughlab-diario-{date.today().isoformat()}.json"
    return Response(
        content=json.dumps(payload, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
