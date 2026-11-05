"""Diario delle prove: elenco, modulo, foto, importazione ed esportazione dei backup."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload, undefer
from starlette.datastructures import FormData, UploadFile

from . import flours
from .db import SessionLocal
from .models import DiaryEntry, DiaryPhoto, Flour, utcnow
from .services.backup import (
    KNEADING_LABELS,
    DiaryData,
    DiaryPhotoData,
    build_backup,
    parse_backup,
)
from .services.diary_form import (
    ALL_COLUMNS,
    SLOT_LABELS,
    blank_values,
    entry_matches,
    entry_view,
    entry_view_recipe,
    form_from_entry,
    new_form,
    parse_fields,
    photo_infos,
    plan_from_form,
)
from .services.fields import (
    clean_text,
)
from .services.images import MAX_PHOTO_BYTES, SLOTS, sniff_image_mime
from .web import RowId, common_ctx, templates

router = APIRouter(prefix="/diario")

MAX_IMPORT_BYTES = 100_000_000
MAX_FORM_BYTES = (len(SLOTS) * MAX_PHOTO_BYTES) + 2_000_000


# --- Modulo -----------------------------------------------------------------------------------












async def _flour_choices() -> list[dict[str, Any]]:
    """Farine dell'archivio tra cui scegliere nel modulo (nome per esteso, W e proteine)."""
    async with SessionLocal() as session:
        flours = (await session.scalars(select(Flour).order_by(Flour.brand, Flour.name))).all()
    return [
        {
            "id": f.id,
            "brand": f.brand or "Altre",
            "label": f"{f.brand} {f.name}".strip(),
            "w": f.w,
            "protein": f.protein,
        }
        for f in flours
    ]












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
        entry_view(entry)
        for entry in entries
        if (not query or entry_matches(entry, query))
        and (recipe_id is None or entry_view_recipe(entry) == recipe_id)
    ]
    recipe_filter = next((i["recipe_name"] for i in items if recipe_id is not None), "")
    return {
        "diary_flours": await _flour_choices() if form is not None else [],
        "diary_items": items,
        "diary_total": total,
        "diary_query": query,
        "diary_recipe": recipe_id,
        "diary_recipe_label": recipe_filter,
        "diary_form": form,
        "diary_message": message,
        "diary_report": report,
        "diary_slots": SLOT_LABELS,
        "diary_kneading": tuple(KNEADING_LABELS.items()),
    }


async def _panel(request: Request, **kwargs: Any) -> HTMLResponse:
    ctx = common_ctx()
    ctx.update(await panel_context(**kwargs))
    return templates.TemplateResponse(request, "partials/diary_panel.html", ctx)


@asynccontextmanager
async def _open_form(
    request: Request, limit: int
) -> AsyncIterator[tuple[FormData, dict[str, str]] | None]:
    """Form multipart con i file temporanei chiusi a fine richiesta; None se il corpo è troppo grande."""
    if _too_large(request, limit):
        yield None
        return
    async with request.form() as form:
        yield form, {k: v for k, v in form.items() if isinstance(v, str)}


# --- Rotte ------------------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
async def diary_list(
    request: Request, q: str = "", recipe: Annotated[int | None, Query(ge=1, le=2_147_483_647)] = None
) -> HTMLResponse:
    return await _panel(request, query=q, recipe_id=recipe)


@router.get("/nuova", response_class=HTMLResponse)
async def diary_new(request: Request) -> HTMLResponse:
    return await _panel(request, form=new_form())


@router.get("/{entry_id:int}/modifica", response_class=HTMLResponse)
async def diary_edit(request: Request, entry_id: RowId) -> HTMLResponse:
    async with SessionLocal() as session:
        entry = await session.get(DiaryEntry, entry_id)
        form = form_from_entry(entry) if entry else None
    if form is None:
        return await _panel(request, message="Voce non trovata.")
    return await _panel(request, form=form)


@router.post("", response_class=HTMLResponse)
async def diary_create(request: Request) -> HTMLResponse:
    async with _open_form(request, MAX_FORM_BYTES) as parsed:
        if parsed is None:
            return await _panel(request, form=new_form(), message="Le foto sono troppo grandi.")
        form, data = parsed
        fields, error = parse_fields(data)
        plan = plan_from_form(data)
        entry = DiaryEntry(external_id=str(uuid4()), extra={}, plan=plan)
        if error is None:
            for column, value in fields.items():
                setattr(entry, column, value)
            error = await _apply_photos(entry, form, data)
        if error is not None:
            failed = new_form({k: data.get(k, "") for k in blank_values()}, plan)
            failed["error"] = error
            return await _panel(request, form=failed)
    async with SessionLocal() as session:
        session.add(entry)
        await session.commit()
    message = "Prova salvata nel diario."
    if data.get("use_stock") == "on":
        used = await flours.consume_stock(plan)
        if used:
            message += " Scalato dalla dispensa: " + "; ".join(used) + "."
    return await _panel(request, message=message)


@router.post("/{entry_id:int}", response_class=HTMLResponse)
async def diary_update(request: Request, entry_id: RowId) -> HTMLResponse:
    async with _open_form(request, MAX_FORM_BYTES) as parsed, SessionLocal() as session:
        entry = await session.get(DiaryEntry, entry_id)
        if entry is None:
            return await _panel(request, message="Voce non trovata.")
        if parsed is None:
            failed = form_from_entry(entry)
            failed["error"] = "Le foto sono troppo grandi."
            return await _panel(request, form=failed)
        form, data = parsed
        photos = photo_infos(entry)
        fields, error = parse_fields(data)
        if error is None:
            for column, value in fields.items():
                setattr(entry, column, value)
            error = await _apply_photos(entry, form, data)
        if error is not None:
            failed = {
                "entry_id": entry_id,
                "data": {k: data.get(k, "") for k in blank_values()},
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
    async with _open_form(request, MAX_IMPORT_BYTES) as parsed:
        if parsed is None:
            return await _panel(request, message="Il file è troppo grande (massimo 100 MB).")
        upload = parsed[0].get("file")
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
