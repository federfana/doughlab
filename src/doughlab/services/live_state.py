"""Stato dell'impasto in corso: controllo di ciò che il browser manda al server."""
from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

MAX_PHASES = 60
MAX_CHECKS = 400
MAX_STATE_BYTES = 100_000


def _number(value: Any, low: float, high: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value) if low <= value <= high else None


def _text(value: Any, limit: int) -> str | None:
    return value[:limit] if isinstance(value, str) else None


def _numbers(value: Any, high_count: int, low: float, high: float) -> list[float] | None:
    if not isinstance(value, list) or len(value) > high_count:
        return None
    cleaned = [_number(item, low, high) for item in value]
    return None if any(item is None for item in cleaned) else [float(i) for i in cleaned if i is not None]


def _flags(value: Any) -> dict[str, bool] | None:
    if not isinstance(value, dict) or len(value) > MAX_CHECKS:
        return None
    return {str(key)[:20]: bool(flag) for key, flag in value.items()}


EPOCH_MS = (0.0, 4_102_444_800_000.0)  # fino al 2100
MAX_EXTRA_MINUTES = 100_000.0


def clean_live_state(raw: Any) -> dict[str, Any] | None:
    """Stato valido e ripulito, oppure None se qualcosa non torna (struttura, tipi, intervalli)."""
    if not isinstance(raw, dict) or not isinstance(raw.get("phases"), list):
        return None
    if not 0 < len(raw["phases"]) <= MAX_PHASES:
        return None
    phases = []
    for phase in raw["phases"]:
        if not isinstance(phase, dict):
            return None
        kind, label, hours = _text(phase.get("kind"), 30), _text(phase.get("label"), 80), _number(phase.get("hours"), 0, 720)
        if kind is None or label is None or hours is None:
            return None
        phases.append({"kind": kind, "label": label, "hours": hours})
    actual = _numbers(raw.get("actual"), len(phases) + 1, *EPOCH_MS)
    extra = _numbers(raw.get("extra"), len(phases), -MAX_EXTRA_MINUTES, MAX_EXTRA_MINUTES)
    started = _number(raw.get("startedAt"), *EPOCH_MS)
    checks, notified = _flags(raw.get("checks")), _flags(raw.get("notified"))
    if not actual or extra is None or started is None or checks is None or notified is None:
        return None
    planned = raw.get("plannedReady")
    dough = raw.get("doughTemp", "")
    return {
        "name": _text(raw.get("name"), 120) or "Impasto",
        "startedAt": started,
        "phases": phases,
        "actual": actual,
        "extra": extra,
        "checks": checks,
        "notified": notified,
        "doughTemp": str(dough)[:10] if isinstance(dough, (str, int, float)) and not isinstance(dough, bool) else "",
        "plannedReady": _text(planned, 40),
    }


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def _fold(line: str) -> str:
    """Righe da 75 byte al massimo, come chiede il formato (le continuazioni iniziano con uno spazio)."""
    data, parts = line.encode(), []
    while len(data) > 75:
        cut = 75
        while cut > 0 and (data[cut] & 0xC0) == 0x80:  # non spezzare un carattere UTF-8
            cut -= 1
        parts.append(data[:cut].decode())
        data = b" " + data[cut:]
    parts.append(data.decode())
    return "\r\n".join(parts)


def _stamp(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y%m%dT%H%M%SZ")


def phase_ends(state: dict[str, Any]) -> list[tuple[int, float]]:
    """Fine prevista di ogni fase non ancora conclusa: `[(indice, ms)]`, dalla fase attuale in poi."""
    phases, actual, extra = state["phases"], state["actual"], state["extra"]
    if len(actual) > len(phases):
        return []  # tutte le fasi sono già concluse
    current = len(actual) - 1
    ends: list[tuple[int, float]] = []
    cursor = actual[current]
    for index in range(current, len(phases)):
        minutes = phases[index]["hours"] * 60 + (extra[index] if index < len(extra) else 0)
        cursor += minutes * 60_000
        ends.append((index, cursor))
    return ends


def live_reminders_ics(state: dict[str, Any], saved_at: int, now_ms: float, slot_minutes: int = 5) -> str | None:
    """File `.ics` con un promemoria alla fine di ogni fase rimasta; None se non c'è nulla da ricordare.

    Gli UID sono stabili (impasto + fase) e SEQUENCE cresce a ogni salvataggio: riscaricarlo dopo uno spostamento
    dei tempi aggiorna gli eventi nel Calendario invece di duplicarli.
    """
    phases, name = state["phases"], state["name"]
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//DoughLab//Impasto in corso//IT", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH"]
    count = 0
    for index, end in phase_ends(state):
        duration = phases[index]["hours"] * 60 + (state["extra"][index] if index < len(state["extra"]) else 0)
        if end < now_ms or duration <= 0:
            continue  # già passata, oppure fase senza durata (ci pensa l'evento della fase prima)
        count += 1
        following = phases[index + 1] if index + 1 < len(phases) else None
        title = f"🍕 {phases[index]['label']} finita" + (f" → ora {following['label']}" if following else "")
        description = f"{name}: fase {index + 1} di {len(phases)}."
        if following:
            minutes = round(following["hours"] * 60 + (state["extra"][index + 1] if index + 1 < len(state["extra"]) else 0))
            description += f" Dopo: {following['label']} ({minutes} min)."
        lines += [
            "BEGIN:VEVENT",
            f"UID:doughlab-live-{int(state['startedAt'])}-{index}@doughlab.local",
            f"DTSTAMP:{_stamp(now_ms)}",
            f"SEQUENCE:{saved_at // 1000}",
            f"DTSTART:{_stamp(end)}",
            f"DTEND:{_stamp(end + slot_minutes * 60_000)}",
            f"SUMMARY:{_escape(title)}",
            f"DESCRIPTION:{_escape(description)}",
            "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_escape(title)}", "TRIGGER:PT0S", "END:VALARM",
            "END:VEVENT",
        ]
    if not count:
        return None
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
