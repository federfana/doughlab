"""Calcolo delle grammature con il sistema baker's percentage.

Nel panificatorio tutto è relativo al 100% di farina. Dato peso panetto
e numero panetti, risolviamo:

    farina * (1 + idratazione + sale + lievito + olio + zucchero) = peso_totale

e ricaviamo tutti i grammi. Il prefermento (biga/poolish/LM) è una
quota della farina totale a cui corrisponde la sua acqua propria.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RecipeStyle(StrEnum):
    NAPOLETANA = "napoletana"
    TEGLIA = "teglia"
    PALA = "pala"
    PINSA = "pinsa"
    ROMANA = "romana"
    PANE = "pane"
    PANETTONE = "panettone"


STYLE_LABELS: dict[RecipeStyle, str] = {
    RecipeStyle.NAPOLETANA: "Napoletana",
    RecipeStyle.TEGLIA: "Teglia",
    RecipeStyle.PALA: "Pala",
    RecipeStyle.PINSA: "Pinsa",
    RecipeStyle.ROMANA: "Romana",
    RecipeStyle.PANE: "Pane",
    RecipeStyle.PANETTONE: "Panettone",
}


@dataclass
class RecipeIngredients:
    """Input: convenzione baker's percentage, tutte le % come frazione (0-1)."""

    panetto_g: float
    n_panetti: int
    hydration_pct: float = 0.60
    salt_pct: float = 0.025
    yeast_pct: float = 0.003
    oil_pct: float = 0.0
    sugar_pct: float = 0.0
    preferment_pct: float = 0.0
    preferment_hydration_pct: float = 1.0
    # Quota (0-1) del lievito totale messa nel prefermento; il resto va nell'impasto finale.
    preferment_yeast_share: float = 1.0


@dataclass
class IngredientWeights:
    """Grammature calcolate: tutto il resto della ricetta parte da qui."""

    flour_g: float
    water_g: float
    salt_g: float
    yeast_g: float
    oil_g: float
    sugar_g: float
    preferment_flour_g: float
    preferment_water_g: float
    preferment_yeast_g: float
    final_dough_flour_g: float
    final_dough_water_g: float
    final_dough_yeast_g: float
    total_g: float


def compute(ri: RecipeIngredients) -> IngredientWeights:
    """Calcola le grammature a partire dalle percentuali."""
    total = ri.panetto_g * ri.n_panetti
    denom = (
        1.0
        + ri.hydration_pct
        + ri.salt_pct
        + ri.yeast_pct
        + ri.oil_pct
        + ri.sugar_pct
    )
    flour = total / denom
    water = flour * ri.hydration_pct
    salt = flour * ri.salt_pct
    yeast = flour * ri.yeast_pct
    oil = flour * ri.oil_pct
    sugar = flour * ri.sugar_pct
    pref_flour = flour * ri.preferment_pct
    # Il prefermento non può contenere più acqua di tutto l'impasto.
    pref_water = min(pref_flour * ri.preferment_hydration_pct, water)
    pref_yeast = yeast * ri.preferment_yeast_share if pref_flour > 0 else 0.0

    return IngredientWeights(
        flour_g=flour,
        water_g=water,
        salt_g=salt,
        yeast_g=yeast,
        oil_g=oil,
        sugar_g=sugar,
        preferment_flour_g=pref_flour,
        preferment_water_g=pref_water,
        preferment_yeast_g=pref_yeast,
        final_dough_flour_g=flour - pref_flour,
        final_dough_water_g=water - pref_water,
        final_dough_yeast_g=yeast - pref_yeast,
        total_g=total,
    )
