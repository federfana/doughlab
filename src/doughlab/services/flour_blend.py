"""Miscele di farine: medie pesate dei dati tecnici e idratazione consigliata."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from .fields import parse_float

MAX_COMPONENTS = 3

# Idratazione indicativa dalla forza W, in linea con le schede dei produttori
# (W 240: 58-62%, W 290: 63-68%, oltre W 320: più del 65%). Una stima, non una misura.
_W_HYDRATION: tuple[tuple[float, tuple[float, float]], ...] = (
    (200, (55, 60)),
    (240, (58, 62)),
    (270, (60, 65)),
    (300, (63, 68)),
    (340, (66, 72)),
    (380, (68, 75)),
    (float("inf"), (70, 78)),
)


class FlourLike(Protocol):
    id: int
    brand: str
    name: str
    w: float | None
    pl: float | None
    protein: float | None
    hydration_min: float | None
    hydration_max: float | None
    method: str
    method_note: str


METHOD_LABELS = {
    "diretto": "solo diretto",
    "indiretto": "solo indiretto",
    "entrambi": "diretto o indiretto",
}


@dataclass(frozen=True)
class Component:
    flour: FlourLike
    share: float  # percentuale sulla farina totale, già normalizzata a 100


@dataclass(frozen=True)
class HydrationAdvice:
    low: float
    high: float
    basis: str  # "produttore", "stima dalla forza W" o "mista"

    @property
    def mid(self) -> float:
        return round((self.low + self.high) / 2, 1)


@dataclass(frozen=True)
class Blend:
    components: tuple[Component, ...]
    entered_pct: float
    w: float | None
    pl: float | None
    protein: float | None
    hydration: HydrationAdvice | None


def estimate_hydration(w: float) -> tuple[float, float]:
    for limit, span in _W_HYDRATION:
        if w <= limit:
            return span
    return _W_HYDRATION[-1][1]


def parse_rows(data: Mapping[str, str]) -> list[tuple[int, float]]:
    """Farine scelte nel form (`flour_id_N` e `flour_pct_N`): id valido, percentuale positiva."""
    rows: list[tuple[int, float]] = []
    seen: set[int] = set()
    for index in range(MAX_COMPONENTS):
        raw = data.get(f"flour_id_{index}", "").strip()
        if not raw.isdecimal() or len(raw) > 9 or int(raw) in seen:
            continue
        pct = parse_float(data.get(f"flour_pct_{index}"), 0, 100)
        if pct is None or pct <= 0:
            continue
        seen.add(int(raw))
        rows.append((int(raw), pct))
    return rows


def _weighted(
    components: tuple[Component, ...], getter: Callable[[FlourLike], float | None]
) -> float | None:
    covered = [(c.share, value) for c in components if (value := getter(c.flour)) is not None]
    total = sum(share for share, _ in covered)
    if total <= 0:
        return None
    return sum(share * value for share, value in covered) / total


def _hydration(components: tuple[Component, ...]) -> HydrationAdvice | None:
    spans: list[tuple[float, float, float, str]] = []
    for component in components:
        flour = component.flour
        if flour.hydration_min is not None and flour.hydration_max is not None:
            spans.append((component.share, flour.hydration_min, flour.hydration_max, "produttore"))
        elif flour.w is not None:
            low, high = estimate_hydration(flour.w)
            spans.append((component.share, low, high, "stima dalla forza W"))
    total = sum(share for share, *_ in spans)
    if total <= 0:
        return None
    bases = {basis for *_, basis in spans}
    return HydrationAdvice(
        low=round(sum(share * low for share, low, _, _ in spans) / total, 1),
        high=round(sum(share * high for share, _, high, _ in spans) / total, 1),
        basis=bases.pop() if len(bases) == 1 else "mista",
    )


def build_blend(rows: list[tuple[FlourLike, float]]) -> Blend | None:
    """Media pesata di W, P/L e proteine (stima: W non è davvero lineare) e idratazione."""
    entered = sum(pct for _, pct in rows)
    if entered <= 0:
        return None
    components = tuple(Component(flour, pct / entered * 100) for flour, pct in rows)
    return Blend(
        components=components,
        entered_pct=entered,
        w=_weighted(components, lambda f: f.w),
        pl=_weighted(components, lambda f: f.pl),
        protein=_weighted(components, lambda f: f.protein),
        hydration=_hydration(components),
    )


def hydration_position(advice: HydrationAdvice, current_pct: float) -> str:
    """`sotto`, `dentro` o `sopra` l'intervallo consigliato (mezzo punto di tolleranza)."""
    if current_pct < advice.low - 0.5:
        return "sotto"
    if current_pct > advice.high + 0.5:
        return "sopra"
    return "dentro"


def blend_label(blend: Blend) -> str:
    """`60% Caputo Nuvola + 40% Agricola Piano Forte 320`."""
    parts = []
    for component in blend.components:
        flour = component.flour
        name = f"{flour.brand} {flour.name}".strip()
        parts.append(f"{component.share:.0f}% {name}" if len(blend.components) > 1 else name)
    return " + ".join(parts)


def method_warnings(blend: Blend, has_preferment: bool) -> list[str]:
    """Avvisi se il piano contraddice un `solo diretto` o un `solo indiretto` dichiarato."""
    warnings = []
    for component in blend.components:
        flour = component.flour
        name = f"{flour.brand} {flour.name}".strip()
        if flour.method == "diretto" and has_preferment:
            warnings.append(f"{name} è indicata solo per impasti diretti, ma il piano usa un prefermento.")
        elif flour.method == "indiretto" and not has_preferment:
            warnings.append(f"{name} è indicata solo per impasti indiretti, ma il piano è diretto: manca il prefermento.")
    return warnings
