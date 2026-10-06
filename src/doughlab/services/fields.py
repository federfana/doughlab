"""Lettura difensiva di valori testuali o numerici (form, JSON importati)."""
from __future__ import annotations

import math
from datetime import UTC, date, datetime
from typing import Any


def clean_text(value: Any, limit: int) -> str:
    if value is None or isinstance(value, (dict, list, bool)):
        return ""
    return str(value).replace("\x00", "").strip()[:limit]


def parse_float(value: Any, low: float, high: float) -> float | None:
    """Numero finito dentro [low, high]; vuoto, illeggibile o NaN/inf danno None."""
    if value is None or isinstance(value, (bool, dict, list)):
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
        if not value:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return min(high, max(low, number))


def parse_int(value: Any, low: int, high: int) -> int | None:
    number = parse_float(value, low, high)
    return None if number is None else round(number)


def parse_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def parse_datetime(value: Any) -> datetime | None:
    """Data e ora ISO (anche con `Z`) come orario naive: UTC se aveva un fuso, altrimenti invariato."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def format_number(value: float | int | None) -> str:
    if value is None:
        return ""
    return f"{value:g}"


def format_minutes(minutes: float) -> str:
    """Durata leggibile: `45 s`, `1 min 15 s`, `30 min`, `2 h 30 min` (mai minuti decimali)."""
    seconds = round(max(0.0, minutes) * 60)
    if seconds == 0:
        return "0 min"
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        mins, secs = divmod(seconds, 60)
        return f"{mins} min" + (f" {secs} s" if secs else "")
    hours, mins = divmod(round(seconds / 60), 60)
    return f"{hours} h" + (f" {mins} min" if mins else "")


def format_hours(hours: float) -> str:
    return format_minutes(hours * 60)
