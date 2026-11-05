"""Impasto in corso: copia sul server dello stato che il browser tiene in `localStorage`.

Il browser resta la fonte primaria (funziona anche offline) e sincronizza in background; il server serve a
non perdere l'impasto se Safari pulisce i dati e a riprenderlo da un altro dispositivo. Vince la scrittura
più recente (`savedAt`, in ms); chiudere l'impasto lascia una «lapide» con lo stato vuoto.
"""
from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select

from .db import SessionLocal
from .models import LiveSession
from .services.live_state import MAX_STATE_BYTES, clean_live_state, live_reminders_ics

router = APIRouter(prefix="/live")

_EPOCH_MS_MAX = 4_102_444_800_000


async def _current(session: Any) -> LiveSession | None:
    result: LiveSession | None = await session.scalar(select(LiveSession).where(LiveSession.id == 1))
    return result


def _payload(row: LiveSession | None) -> dict[str, Any]:
    return {"savedAt": row.saved_at if row else 0, "state": row.state if row else None}


@router.get("")
async def live_get() -> JSONResponse:
    async with SessionLocal() as session:
        return JSONResponse(_payload(await _current(session)), headers={"Cache-Control": "no-store"})


@router.put("")
async def live_put(request: Request) -> JSONResponse:
    raw = await request.body()
    if len(raw) > MAX_STATE_BYTES:
        return JSONResponse({"error": "stato troppo grande"}, status_code=413)
    try:
        body = json.loads(raw)
    except ValueError:
        return JSONResponse({"error": "JSON non valido"}, status_code=400)
    saved_at = body.get("savedAt") if isinstance(body, dict) else None
    if isinstance(saved_at, bool) or not isinstance(saved_at, (int, float)) or not 0 < saved_at < _EPOCH_MS_MAX:
        return JSONResponse({"error": "savedAt non valido"}, status_code=400)
    state = body.get("state")
    cleaned = None if state is None else clean_live_state(state)
    if state is not None and cleaned is None:
        return JSONResponse({"error": "stato non valido"}, status_code=400)
    async with SessionLocal() as session:
        row = await _current(session)
        if row is not None and row.saved_at > saved_at:
            return JSONResponse(_payload(row), status_code=409)  # sul server c'è già qualcosa di più recente
        if row is None:
            row = LiveSession(id=1)
            session.add(row)
        row.state, row.saved_at = cleaned, int(saved_at)
        await session.commit()
        return JSONResponse(_payload(row))


@router.get("/calendar.ics")
async def live_calendar() -> Response:
    """Promemoria nel Calendario: uno alla fine di ogni fase rimasta dell'impasto in corso."""
    async with SessionLocal() as session:
        row = await _current(session)
    state = row.state if row else None
    content = live_reminders_ics(state, row.saved_at, time.time() * 1000) if row and state else None
    if content is None:
        return Response("Nessuna fase in corso da ricordare.", status_code=404, media_type="text/plain; charset=utf-8")
    return Response(
        content=content,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="doughlab-promemoria.ics"', "Cache-Control": "no-store"},
    )
