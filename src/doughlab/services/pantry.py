"""Magazzino delle farine: grammi in dispensa e consumo di un impasto."""
from __future__ import annotations

import math
from typing import Any

MAX_STOCK_G = 1_000_000.0
MAX_PLAN_FLOUR_G = 100_000.0


def format_grams(value: float) -> str:
    """Grammi con il punto delle migliaia: `2.500 g`."""
    return f"{round(value):,}".replace(",", ".") + " g"


def _number(value: Any, low: float, high: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value) if low <= value <= high else None


def plan_consumption(plan: Any) -> list[tuple[int, float]]:
    """Grammi di farina usati per ogni farina scelta nel piano: `[(id farina, grammi)]`.

    La farina totale è quella dell'impasto con il prefermento; si divide per le percentuali della miscela.
    """
    if not isinstance(plan, dict):
        return []
    weights, flours = plan.get("ingredients"), plan.get("flours")
    if not isinstance(weights, dict) or not isinstance(flours, list):
        return []
    total = _number(weights.get("flour_g"), 0.0, MAX_PLAN_FLOUR_G)
    if not total:
        return []
    grams: dict[int, float] = {}
    for item in flours:
        if not isinstance(item, dict):
            continue
        flour_id, pct = item.get("id"), _number(item.get("pct"), 0.0, 100.0)
        if isinstance(flour_id, bool) or not isinstance(flour_id, int) or not pct:
            continue
        grams[flour_id] = grams.get(flour_id, 0.0) + total * pct / 100
    return list(grams.items())
