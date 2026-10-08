"""Farine consigliate per un impasto: forza W e idratazione adatte a stile, ore di maturazione e metodo."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .fields import format_hours
from .flour_blend import FlourLike, estimate_hydration

# Forza W utile per durata totale della maturazione (ore): più a lungo si matura, più forza serve.
_W_BY_HOURS: tuple[tuple[float, tuple[float, float]], ...] = (
    (10, (220, 280)),
    (26, (260, 320)),
    (50, (300, 350)),
    (float("inf"), (320, 380)),
)
# Stili che chiedono più forza a parità di tempi (impasti molto idratati, pani).
_STYLE_W_OFFSET = {"teglia": 20, "pala": 20, "pinsa": 10, "pane": 20, "panettone": 60}
MAX_SCORE = 5.0
# Parole che, nella scheda della farina, indicano che è pensata per lo stile.
_STYLE_WORDS = {
    "napoletana": ("napoletan", "pizza"),
    "romana": ("pizza",),
    "teglia": ("teglia",),
    "pala": ("pala",),
    "pinsa": ("pinsa",),
    "pane": ("pane",),
}


@dataclass(frozen=True)
class Suggestion:
    flour: FlourLike
    score: float
    reason: str


def target_w(total_hours: float, hydration_pct: float, style: str) -> tuple[float, float]:
    base = next(span for limit, span in _W_BY_HOURS if total_hours <= limit)
    offset = _STYLE_W_OFFSET.get(style, 0) + (20 if hydration_pct >= 70 else 0) + (10 if hydration_pct >= 75 else 0)
    return base[0] + offset, base[1] + offset


def _gap(value: float, low: float, high: float) -> float:
    return 0.0 if low <= value <= high else min(abs(value - low), abs(value - high))


def suggest_flours(
    flours: Iterable[FlourLike],
    *,
    style: str,
    total_hours: float,
    hydration_pct: float,
    has_preferment: bool,
    limit: int = 3,
) -> list[Suggestion]:
    """Le farine di marca che meglio si adattano: una per marca finché possibile, poi le migliori."""
    low, high = target_w(total_hours, hydration_pct, style)
    scored: list[Suggestion] = []
    for flour in flours:
        kind = getattr(flour, "kind", "").lower()
        if flour.brand == "Generica" or flour.w is None:
            continue
        if "integrale" in kind and style != "pane":
            continue
        if (flour.method == "diretto" and has_preferment) or (flour.method == "indiretto" and not has_preferment):
            continue
        w_gap = _gap(flour.w, low, high)
        if flour.hydration_min is not None and flour.hydration_max is not None:
            producer, h_low, h_high = True, flour.hydration_min, flour.hydration_max
        else:
            producer = False
            h_low, h_high = estimate_hydration(flour.w)
        h_gap = _gap(hydration_pct, h_low, h_high)
        text = f"{flour.name} {getattr(flour, 'use', '')}".lower()
        for_style = any(word in text for word in _STYLE_WORDS.get(style, ()))
        # La W conta di più; l'idratazione si può correggere (il piano lo segnala), quindi pesa meno.
        score = w_gap / 10 + h_gap * 0.7 - (0.3 if producer else 0.0) - (0.2 if for_style else 0.0)
        if score >= MAX_SCORE:
            continue
        w_where = "nell'intervallo" if w_gap == 0 else "vicina all'intervallo"
        w_text = f"W {flour.w:.0f} {w_where} {low:.0f}-{high:.0f}"
        h_text = (
            f"idratazione {hydration_pct:g}% {'nel' if h_gap == 0 else 'fuori dal'} "
            f"{'range del produttore' if producer else 'range stimato'} {h_low:g}-{h_high:g}%"
        )
        scored.append(Suggestion(flour, score, f"{w_text} per {format_hours(total_hours)}; {h_text}"))
    scored.sort(key=lambda s: (s.score, abs((s.flour.w or 0) - (low + high) / 2)))
    picked: list[Suggestion] = []
    brands: set[str] = set()
    for suggestion in scored:
        if suggestion.flour.brand not in brands and len(picked) < limit:
            picked.append(suggestion)
            brands.add(suggestion.flour.brand)
    for suggestion in scored:
        if len(picked) < limit and suggestion not in picked:
            picked.append(suggestion)
    picked.sort(key=lambda s: s.score)
    return picked
