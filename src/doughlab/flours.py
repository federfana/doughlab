"""Farine: elenco e modifica, farine predefinite e calcolo della miscela per il piano."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from .db import SessionLocal
from .models import AppSetting, Flour
from .services.fields import clean_text, format_number, parse_float
from .services.flour_blend import (
    METHOD_LABELS,
    Blend,
    blend_label,
    build_blend,
    hydration_position,
    method_warnings,
    parse_rows,
)
from .services.flour_seed import DRAFT_NOTE, FLOUR_SEEDS, SEED_CORRECTIONS, SEED_SINCE, SEED_VERSION
from .services.flour_suggest import suggest_flours
from .web import RowId, common_ctx, templates

router = APIRouter(prefix="/farine")

TEXT_LIMITS = {"brand": 80, "name": 80, "kind": 60, "use": 200, "notes": 4_000, "method_note": 200}
NUMBER_LIMITS = {
    "w": (0.0, 1_000.0),
    "pl": (0.0, 10.0),
    "protein": (0.0, 30.0),
    "hydration_min": (30.0, 200.0),
    "hydration_max": (30.0, 200.0),
}


SEED_VERSION_KEY = "flour_seed_version"
# Campi che la sincronizzazione riempie nelle predefinite quando nel database mancano.
FILL_FIELDS = ("kind", "w", "pl", "protein", "hydration_min", "hydration_max", "hydration_note", "use")


_NUMBER_COLUMNS = ("w", "pl", "protein", "hydration_min", "hydration_max")
_TEXT_COLUMNS = ("name", "kind", "hydration_note", "method", "method_note", "use", "notes", "source_url")


def _apply_seed(flour: Flour, seed: dict[str, Any]) -> None:
    """Sostituisce i dati tecnici di una predefinita con quelli del seme (anche i vuoti)."""
    for column in _NUMBER_COLUMNS:
        setattr(flour, column, seed.get(column))
    for column in _TEXT_COLUMNS:
        setattr(flour, column, seed.get(column) or "")


async def _set_seed_version(session: Any, version: int) -> None:
    row = await session.get(AppSetting, SEED_VERSION_KEY)
    if row is None:
        session.add(AppSetting(key=SEED_VERSION_KEY, value=str(version)))
    else:
        row.value = str(version)


async def seed_if_empty() -> None:
    """Alla prima apertura carica le farine predefinite; poi le tue modifiche restano tue."""
    async with SessionLocal() as session:
        if await session.scalar(select(func.count(Flour.id))):
            return
        session.add_all(Flour(builtin=True, **seed) for seed in FLOUR_SEEDS)
        await _set_seed_version(session, SEED_VERSION)
        await session.commit()


async def sync_builtin_seeds() -> int:
    """Allinea le predefinite alla versione corrente dell'archivio; restituisce quante ne ha aggiunte.

    Ad ogni avvio corregge le predefinite della versione 2 ancora con la nota provvisoria (mai
    modificate da te). Una volta per versione aggiunge le nuove e riempie i dati mancanti. Non
    rimette le farine eliminate e non sovrascrive altri valori presenti.
    """
    async with SessionLocal() as session:
        row = await session.get(AppSetting, SEED_VERSION_KEY)
        stored = int(row.value) if row is not None and row.value.isdecimal() else 1
        existing = {(f.brand, f.name): f for f in await session.scalars(select(Flour))}
        seeds = {(s["brand"], s["name"]): s for s in FLOUR_SEEDS}
        corrected = False
        for old_key, new_key in SEED_CORRECTIONS.items():
            draft = existing.get(old_key)
            if draft is not None and draft.builtin and draft.notes == DRAFT_NOTE:
                _apply_seed(draft, seeds[new_key])
                existing[new_key] = existing.pop(old_key)
                corrected = True
        added = 0
        if stored < SEED_VERSION:
            for seed in FLOUR_SEEDS:
                flour = existing.get((seed["brand"], seed["name"]))
                if flour is None:
                    if SEED_SINCE.get((seed["brand"], seed["name"]), 1) > stored:
                        session.add(Flour(builtin=True, **seed))
                        added += 1
                elif flour.builtin:
                    for field in FILL_FIELDS:
                        if field in seed and getattr(flour, field) in (None, ""):
                            setattr(flour, field, seed[field])
            await _set_seed_version(session, SEED_VERSION)
        if stored < SEED_VERSION or corrected:
            await session.commit()
        return added


async def backfill_builtin_methods() -> None:
    """Dopo l'aggiunta delle colonne `method`: riempie le predefinite già presenti nel database."""
    methods = {(s["brand"], s["name"]): s for s in FLOUR_SEEDS if s.get("method") or s.get("method_note")}
    async with SessionLocal() as session:
        for flour in await session.scalars(select(Flour).where(Flour.builtin.is_(True))):
            seed = methods.get((flour.brand, flour.name))
            if seed and not flour.method and not flour.method_note:
                flour.method, flour.method_note = seed["method"], seed["method_note"]
        await session.commit()


async def restore_builtin() -> int:
    """Aggiunge le predefinite mancanti senza toccare quelle già presenti."""
    async with SessionLocal() as session:
        existing = {(f.brand, f.name) for f in await session.scalars(select(Flour))}
        missing = [s for s in FLOUR_SEEDS if (s["brand"], s["name"]) not in existing]
        session.add_all(Flour(builtin=True, **seed) for seed in missing)
        await session.commit()
        return len(missing)


# --- Viste ------------------------------------------------------------------------------------


def _numbers(flour: Flour) -> str:
    parts = []
    if flour.w is not None:
        parts.append(f"W {format_number(flour.w)}")
    if flour.pl is not None:
        parts.append(f"P/L {format_number(flour.pl).replace('.', ',')}")
    if flour.protein is not None:
        parts.append(f"proteine {format_number(flour.protein).replace('.', ',')}%")
    return " · ".join(parts) or "dati tecnici non indicati"


def _hydration_text(flour: Flour) -> str:
    if flour.hydration_min is None or flour.hydration_max is None:
        return ""
    span = f"{format_number(flour.hydration_min)}-{format_number(flour.hydration_max)}%"
    return f"{span} ({flour.hydration_note})" if flour.hydration_note else span


def _item(flour: Flour) -> dict[str, Any]:
    return {
        "id": flour.id,
        "brand": flour.brand,
        "name": flour.name,
        "kind": flour.kind,
        "numbers": _numbers(flour),
        "hydration": _hydration_text(flour),
        "method": METHOD_LABELS.get(flour.method, ""),
        "method_note": flour.method_note,
        "use": flour.use,
        "notes": flour.notes,
        "source_url": flour.source_url if flour.source_url.startswith("https://") else "",
        "builtin": flour.builtin,
    }


def _values(flour: Flour | None) -> dict[str, str]:
    values = dict.fromkeys((*TEXT_LIMITS, *NUMBER_LIMITS, "method"), "")
    if flour is not None:
        values["method"] = flour.method
        for key in TEXT_LIMITS:
            values[key] = getattr(flour, key) or ""
        for key in NUMBER_LIMITS:
            values[key] = format_number(getattr(flour, key))
    return values


async def panel_context(
    form: dict[str, Any] | None = None, message: str | None = None, query: str = ""
) -> dict[str, Any]:
    async with SessionLocal() as session:
        flours = (
            await session.scalars(select(Flour).order_by(Flour.brand, Flour.name))
        ).all()
    words = query.lower().split()
    shown = [
        f for f in flours
        if all(w in f"{f.brand} {f.name} {f.kind} {f.use}".lower() for w in words)
    ]
    groups: dict[str, list[dict[str, Any]]] = {}
    for flour in shown:
        groups.setdefault(flour.brand or "Altre", []).append(_item(flour))
    return {
        "flours_groups": list(groups.items()),
        "flours_total": len(flours),
        "flours_shown": len(shown),
        "flours_query": query,
        "flours_form": form,
        "flours_message": message,
        "flours_options": [
            {"id": f.id, "brand": f.brand or "Altre", "label": f.name} for f in flours
        ],
        "flours_brands": sorted({f.brand for f in flours if f.brand}),
    }


async def _panel(request: Request, **kwargs: Any) -> HTMLResponse:
    ctx = common_ctx()
    ctx.update(await panel_context(**kwargs))
    ctx["flours_oob"] = True
    return templates.TemplateResponse(request, "partials/flours_panel.html", ctx)


def _parse(data: dict[str, str]) -> tuple[dict[str, Any], str | None]:
    fields: dict[str, Any] = {key: clean_text(data.get(key), limit) for key, limit in TEXT_LIMITS.items()}
    for key, (low, high) in NUMBER_LIMITS.items():
        fields[key] = parse_float(data.get(key), low, high)
    method = data.get("method", "").strip()
    fields["method"] = method if method in METHOD_LABELS else ""
    if not fields["name"]:
        return fields, "Dai un nome alla farina."
    low, high = fields["hydration_min"], fields["hydration_max"]
    if (low is None) != (high is None):
        return fields, "Per l'idratazione consigliata servono entrambi gli estremi, oppure nessuno."
    if low is not None and high is not None and low > high:
        return fields, "L'idratazione minima non può superare la massima."
    return fields, None


# --- Rotte ------------------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
async def flours_list(request: Request, q: str = Query("", max_length=100)) -> HTMLResponse:
    return await _panel(request, query=q)


@router.get("/nuova", response_class=HTMLResponse)
async def flour_new(request: Request) -> HTMLResponse:
    return await _panel(request, form={"flour_id": None, "data": _values(None), "error": None})


@router.get("/{flour_id:int}/modifica", response_class=HTMLResponse)
async def flour_edit(request: Request, flour_id: RowId) -> HTMLResponse:
    async with SessionLocal() as session:
        flour = await session.get(Flour, flour_id)
        form = {"flour_id": flour.id, "data": _values(flour), "error": None} if flour else None
    if form is None:
        return await _panel(request, message="Farina non trovata.")
    return await _panel(request, form=form)


async def _save(request: Request, flour_id: int | None) -> HTMLResponse:
    form = await request.form()
    data = {k: str(v) for k, v in form.items()}
    fields, error = _parse(data)
    if error is None:
        async with SessionLocal() as session:
            flour = await session.get(Flour, flour_id) if flour_id else Flour()
            if flour is None:
                return await _panel(request, message="Farina non trovata.")
            for key, value in fields.items():
                setattr(flour, key, value)
            session.add(flour)
            try:
                await session.commit()
            except IntegrityError:
                error = "Esiste già una farina con questo produttore e questo nome."
        if error is None:
            return await _panel(request, message=f"Farina «{fields['name']}» salvata.")
    shown = {k: data.get(k, "") for k in _values(None)}
    return await _panel(request, form={"flour_id": flour_id, "data": shown, "error": error})


@router.post("", response_class=HTMLResponse)
async def flour_create(request: Request) -> HTMLResponse:
    return await _save(request, None)


@router.post("/{flour_id:int}", response_class=HTMLResponse)
async def flour_update(request: Request, flour_id: RowId) -> HTMLResponse:
    return await _save(request, flour_id)


@router.post("/{flour_id:int}/elimina", response_class=HTMLResponse)
async def flour_delete(request: Request, flour_id: RowId) -> HTMLResponse:
    async with SessionLocal() as session:
        flour = await session.get(Flour, flour_id)
        if flour is not None:
            await session.delete(flour)
            await session.commit()
    return await _panel(request, message="Farina eliminata. Le prove e le ricette già salvate restano.")


@router.post("/ripristina", response_class=HTMLResponse)
async def flours_restore(request: Request) -> HTMLResponse:
    added = await restore_builtin()
    return await _panel(
        request,
        message=f"Aggiunte {added} farine predefinite." if added else "Le farine predefinite ci sono già tutte.",
    )


# --- Miscela nel piano ------------------------------------------------------------------------


async def blend_context(
    data: dict[str, str], current_hydration_pct: float, has_preferment: bool = False
) -> dict[str, Any]:
    """Miscela scelta nel form del piano, con statistiche e idratazione consigliata."""
    rows = parse_rows(data)
    if not rows:
        return {"flour_blend": None}
    async with SessionLocal() as session:
        found = {
            f.id: f
            for f in await session.scalars(select(Flour).where(Flour.id.in_([i for i, _ in rows])))
        }
    blend = build_blend([(found[i], pct) for i, pct in rows if i in found])
    if blend is None:
        return {"flour_blend": None}
    return {
        "flour_blend": blend,
        "flour_position": (
            hydration_position(blend.hydration, current_hydration_pct) if blend.hydration else None
        ),
        "flour_current_hydration": round(current_hydration_pct, 1),
        "flour_normalized": abs(blend.entered_pct - 100) > 0.5,
        "flour_warnings": method_warnings(blend, has_preferment),
        "flour_methods": [
            (c.flour, METHOD_LABELS.get(c.flour.method, ""))
            for c in blend.components
            if c.flour.method or c.flour.method_note
        ],
    }


async def suggest_context(
    *, style: str, total_hours: float, hydration_pct: float, has_preferment: bool
) -> dict[str, Any]:
    """Farine consigliate per stile, durata, idratazione e metodo del piano."""
    async with SessionLocal() as session:
        flours = list(await session.scalars(select(Flour)))
    return {
        "flour_suggestions": suggest_flours(
            flours,
            style=style,
            total_hours=total_hours,
            hydration_pct=hydration_pct,
            has_preferment=has_preferment,
        )
    }


def snapshot_extras(blend: Blend | None) -> dict[str, Any]:
    """Cosa aggiungere allo snapshot del piano: serve a Diario e ricette."""
    if blend is None:
        return {}
    return {
        "flours": [
            {"id": c.flour.id, "brand": c.flour.brand, "name": c.flour.name, "pct": round(c.share, 1)}
            for c in blend.components
        ],
        "flour_label": blend_label(blend),
        "flour_w": None if blend.w is None else round(blend.w),
        "flour_protein": None if blend.protein is None else round(blend.protein, 1),
    }
