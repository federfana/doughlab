"""Controlli minimi sulle immagini caricate o importate."""
from __future__ import annotations

import base64
import binascii
from typing import Any

MAX_PHOTO_BYTES = 12_000_000
SLOTS = ("main", "extra1", "extra2", "extra3", "extra4")
DEFAULT_PHOTO_SETTINGS: dict[str, Any] = {
    "fit": "contain", "position": "center", "x": 0.5, "y": 0.5, "zoom": 1, "confirmed": True,
}


def sniff_image_mime(data: bytes) -> str | None:
    """Riconosce solo JPEG, PNG e WebP dai primi byte: il tipo dichiarato dal client non conta."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def decode_data_url(value: Any) -> tuple[str, bytes] | None:
    if not isinstance(value, str) or not value.startswith("data:"):
        return None
    header, _, payload = value.partition(",")
    if ";base64" not in header or len(payload) > MAX_PHOTO_BYTES * 4 // 3 + 16:
        return None
    try:
        raw = base64.b64decode(payload)
    except (binascii.Error, ValueError):
        return None
    mime = sniff_image_mime(raw)
    return (mime, raw) if mime and len(raw) <= MAX_PHOTO_BYTES else None


def encode_data_url(mime: str, data: bytes) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def normalize_photo_settings(raw: Any) -> dict[str, Any]:
    """Impostazioni di inquadratura del backup, ridotte ai soli valori usati dalla pagina."""
    settings = dict(DEFAULT_PHOTO_SETTINGS)
    if not isinstance(raw, dict):
        return settings
    if raw.get("fit") in {"contain", "cover"}:
        settings["fit"] = raw["fit"]
    for axis in ("x", "y"):
        value = raw.get(axis)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1:
            settings[axis] = float(value)
    zoom = raw.get("zoom")
    if isinstance(zoom, (int, float)) and not isinstance(zoom, bool) and 1 <= zoom <= 5:
        settings["zoom"] = float(zoom)
    if isinstance(raw.get("confirmed"), bool):
        settings["confirmed"] = raw["confirmed"]
    return settings
