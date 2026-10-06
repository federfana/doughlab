"""Lettura e scrittura dei backup di Sibellutu Pizza Lab (stesso schema `entries`).

Il formato ha tutti i valori come stringhe; qui diventano numeri e testo con limiti.
Le chiavi sconosciute finiscono in `extra` e tornano nell'export, così non si perde nulla.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from .fields import clean_text, format_number, parse_date, parse_datetime, parse_float, parse_int
from .images import (
    DEFAULT_PHOTO_SETTINGS,
    SLOTS,
    decode_data_url,
    encode_data_url,
    normalize_photo_settings,
)

MAX_ENTRIES = 5000
MAX_EXTRA_BYTES = 20_000
MAX_PLAN_BYTES = 100_000

# chiave Pizza Lab -> (colonna, lunghezza massima)
TEXT_FIELDS: dict[str, tuple[str, int]] = {
    "name": ("name", 120),
    "pizzaType": ("pizza_type", 60),
    "preferment": ("preferment", 60),
    "oven": ("oven", 80),
    "flour": ("flour", 200),
    "bakeTime": ("bake_time", 40),
    "bakeSetup": ("bake_setup", 200),
    "ingredients": ("ingredients", 20_000),
    "process": ("process", 20_000),
    "bake": ("bake", 5_000),
    "notes": ("notes", 20_000),
    "nextChanges": ("next_changes", 5_000),
    "tags": ("tags", 200),
}
# chiave Pizza Lab -> (colonna, minimo, massimo)
FLOAT_FIELDS: dict[str, tuple[str, float, float]] = {
    "flourW": ("flour_w", 0, 1_000),
    "protein": ("protein", 0, 100),
    "hydration": ("hydration", 0, 200),
    "coldHours": ("cold_hours", 0, 2_000),
    "roomHours": ("room_hours", 0, 2_000),
    "doughBallWeight": ("dough_ball_weight", 0, 5_000),
    "doughTemp": ("dough_temp", -20, 100),
    "bakeTemp": ("bake_temp", 0, 1_000),
}
_HANDLED_KEYS = (
    {"id", "date", "rating", "doughBallCount", "photos", "photoLabels", "photoSettings",
     "updatedAt", "doughlab"}
    | set(TEXT_FIELDS)
    | set(FLOAT_FIELDS)
)


@dataclass
class DiaryPhotoData:
    slot: str
    mime: str
    data: bytes
    label: str = ""
    settings: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_PHOTO_SETTINGS))


@dataclass
class DiaryData:
    external_id: str
    fields: dict[str, Any]
    photos: list[DiaryPhotoData] = field(default_factory=list)
    updated_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseResult:
    entries: list[DiaryData] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_rating(value: Any) -> float | None:
    """Voto da 0.5 a 5 a mezzi punti; vuoto o 0 significa nessun voto."""
    number = parse_float(value, 0, 5)
    if number is None:
        return None
    rounded = round(number * 2) / 2
    return rounded or None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _small_json(value: Any, limit: int) -> bool:
    try:
        return len(json.dumps(value)) <= limit
    except (TypeError, ValueError):
        return False


def _parse_entry(item: dict[str, Any]) -> tuple[DiaryData, list[str]]:
    warnings: list[str] = []
    fields: dict[str, Any] = {}
    for key, (column, limit) in TEXT_FIELDS.items():
        fields[column] = clean_text(item.get(key), limit)
    for key, (column, low, high) in FLOAT_FIELDS.items():
        fields[column] = parse_float(item.get(key), low, high)
    fields["dough_ball_count"] = parse_int(item.get("doughBallCount"), 0, 1_000)
    fields["rating"] = parse_rating(item.get("rating"))
    fields["name"] = fields["name"] or "Senza nome"

    updated_at = parse_datetime(item.get("updatedAt"))
    fields["date"] = (
        parse_date(item.get("date")) or (updated_at.date() if updated_at else date.today())
    )

    photos_raw = _dict(item.get("photos"))
    labels = _dict(item.get("photoLabels"))
    settings = _dict(item.get("photoSettings"))
    photos: list[DiaryPhotoData] = []
    for slot in SLOTS:
        raw = photos_raw.get(slot)
        if not raw:
            continue
        decoded = decode_data_url(raw)
        if decoded is None:
            warnings.append(f"«{fields['name']}»: la foto {slot} non è valida e viene ignorata")
            continue
        photos.append(
            DiaryPhotoData(
                slot=slot,
                mime=decoded[0],
                data=decoded[1],
                label=clean_text(labels.get(slot), 120),
                settings=normalize_photo_settings(settings.get(slot)),
            )
        )

    block = item.get("doughlab")
    if isinstance(block, dict):
        if isinstance(block.get("plan"), dict) and _small_json(block["plan"], MAX_PLAN_BYTES):
            fields["plan"] = block["plan"]
        fields["started_at"] = parse_datetime(block.get("startedAt"))
        fields["ready_at"] = parse_datetime(block.get("readyAt"))

    extra = {key: value for key, value in item.items() if key not in _HANDLED_KEYS}
    if not _small_json(extra, MAX_EXTRA_BYTES):
        warnings.append(f"«{fields['name']}»: campi sconosciuti troppo grandi, ignorati")
        extra = {}

    external_id = clean_text(item.get("id"), 64) or str(uuid4())
    return DiaryData(external_id, fields, photos, updated_at, extra), warnings


def parse_backup(raw: bytes | str) -> ParseResult:
    """Legge un backup; `ValueError` se il file non è un JSON con un elenco `entries`."""
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError("Il file non è un JSON valido") from error
    entries = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise ValueError("Non trovo l'elenco `entries`: non sembra un backup di Pizza Lab")

    result = ParseResult()
    for index, item in enumerate(entries[:MAX_ENTRIES], start=1):
        if not isinstance(item, dict):
            result.warnings.append(f"Voce {index}: formato non valido, ignorata")
            continue
        entry, warnings = _parse_entry(item)
        result.entries.append(entry)
        result.warnings.extend(warnings)
    if len(entries) > MAX_ENTRIES:
        result.warnings.append(f"Importate solo le prime {MAX_ENTRIES} voci su {len(entries)}")
    return result


def to_backup_entry(entry: DiaryData) -> dict[str, Any]:
    out: dict[str, Any] = dict(entry.extra)
    fields = entry.fields
    out["id"] = entry.external_id
    for key, (column, _limit) in TEXT_FIELDS.items():
        out[key] = fields.get(column) or ""
    for key, (column, _low, _high) in FLOAT_FIELDS.items():
        out[key] = format_number(fields.get(column))
    out["doughBallCount"] = format_number(fields.get("dough_ball_count"))
    out["rating"] = format_number(fields.get("rating"))
    out["date"] = fields["date"].isoformat()

    by_slot = {photo.slot: photo for photo in entry.photos}
    out["photos"] = {
        slot: encode_data_url(by_slot[slot].mime, by_slot[slot].data) if slot in by_slot else ""
        for slot in SLOTS
    }
    out["photoLabels"] = {
        slot: by_slot[slot].label if slot in by_slot else "" for slot in SLOTS[1:]
    }
    out["photoSettings"] = {
        slot: by_slot[slot].settings if slot in by_slot else dict(DEFAULT_PHOTO_SETTINGS)
        for slot in SLOTS
    }
    if entry.updated_at:
        out["updatedAt"] = entry.updated_at.isoformat(timespec="milliseconds") + "Z"

    doughlab: dict[str, Any] = {}
    if fields.get("plan"):
        doughlab["plan"] = fields["plan"]
    if fields.get("started_at"):
        doughlab["startedAt"] = fields["started_at"].isoformat(timespec="minutes")
    if fields.get("ready_at"):
        doughlab["readyAt"] = fields["ready_at"].isoformat(timespec="minutes")
    if doughlab:
        out["doughlab"] = doughlab
    return out


def build_backup(entries: list[DiaryData]) -> dict[str, Any]:
    return {"app": "DoughLab", "version": "1", "entries": [to_backup_entry(e) for e in entries]}
