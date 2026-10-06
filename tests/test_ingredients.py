"""Test del calcolatore ingredienti (baker's percentage)."""
from __future__ import annotations

import pytest

from doughlab.services.ingredients import RecipeIngredients, compute


def test_total_mass_matches_panetti() -> None:
    ri = RecipeIngredients(panetto_g=250, n_panetti=4, hydration_pct=0.60,
                           salt_pct=0.025, yeast_pct=0.003)
    w = compute(ri)
    assert w.total_g == pytest.approx(1000.0)
    assert w.flour_g + w.water_g + w.salt_g + w.yeast_g + w.oil_g + w.sugar_g \
        == pytest.approx(1000.0, rel=1e-6)


def test_hydration_ratio() -> None:
    ri = RecipeIngredients(panetto_g=250, n_panetti=4, hydration_pct=0.65,
                           salt_pct=0.025, yeast_pct=0.003)
    w = compute(ri)
    assert w.water_g / w.flour_g == pytest.approx(0.65)


def test_salt_ratio() -> None:
    ri = RecipeIngredients(panetto_g=250, n_panetti=4, hydration_pct=0.60,
                           salt_pct=0.028, yeast_pct=0.002)
    w = compute(ri)
    assert w.salt_g / w.flour_g == pytest.approx(0.028)


def test_preferment_split() -> None:
    ri = RecipeIngredients(panetto_g=500, n_panetti=2, hydration_pct=0.70,
                           salt_pct=0.022, yeast_pct=0.001,
                           preferment_pct=0.30, preferment_hydration_pct=0.45)
    w = compute(ri)
    assert w.preferment_flour_g == pytest.approx(w.flour_g * 0.30)
    assert w.preferment_water_g == pytest.approx(w.preferment_flour_g * 0.45)
    assert w.final_dough_flour_g == pytest.approx(w.flour_g - w.preferment_flour_g)
    assert w.final_dough_water_g == pytest.approx(w.water_g - w.preferment_water_g)


def test_preferment_water_never_exceeds_total_water() -> None:
    ri = RecipeIngredients(panetto_g=500, n_panetti=2, hydration_pct=0.60,
                           salt_pct=0.022, yeast_pct=0.001,
                           preferment_pct=1.0, preferment_hydration_pct=1.5)
    w = compute(ri)
    assert w.final_dough_water_g >= 0
    assert w.preferment_water_g == pytest.approx(w.water_g)


def test_oil_included_in_total() -> None:
    ri = RecipeIngredients(panetto_g=800, n_panetti=1, hydration_pct=0.75,
                           salt_pct=0.025, yeast_pct=0.002, oil_pct=0.03)
    w = compute(ri)
    assert w.oil_g / w.flour_g == pytest.approx(0.03)
    assert (w.flour_g + w.water_g + w.salt_g + w.yeast_g + w.oil_g) \
        == pytest.approx(800.0, rel=1e-6)
