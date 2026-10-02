"""Test del modello di fermentazione (Q10)."""
from __future__ import annotations

import numpy as np

from doughlab.services.fermentation import (
    YEAST_PARAMS,
    YeastKind,
    rate,
    simulate,
    suggest_yeast_pct,
)
from doughlab.services.thermal import (
    Container,
    Environment,
    ThermalSegment,
)
from doughlab.services.thermal import (
    simulate as simulate_thermal,
)


def test_rate_at_t_ref_equals_k_ref() -> None:
    p = YEAST_PARAMS[YeastKind.FRESH]
    assert abs(float(rate(p.t_ref_c, YeastKind.FRESH)) - p.k_ref) < 1e-9


def test_q10_doubles_every_10c() -> None:
    """Verifica che il rapporto fra k(T+10) e k(T) sia esattamente Q10."""
    p = YEAST_PARAMS[YeastKind.FRESH]
    r1 = float(rate(20.0, YeastKind.FRESH))
    r2 = float(rate(30.0, YeastKind.FRESH))
    assert abs(r2 / r1 - p.q10) < 1e-6


def test_dry_is_stronger_than_fresh() -> None:
    assert YEAST_PARAMS[YeastKind.DRY].k_ref > YEAST_PARAMS[YeastKind.FRESH].k_ref


def test_fermentation_monotone() -> None:
    seg = ThermalSegment(hours=24, ambient_c=4,
                         container=Container.MASS_BOX,
                         environment=Environment.FRIDGE_HOME)
    curve = simulate_thermal([seg], initial_c=22.0)
    res = simulate(curve, YeastKind.FRESH, yeast_pct=0.3, target_work=24.0)
    assert (np.diff(res.cumulative) >= -1e-9).all()


def test_suggested_pct_hits_target() -> None:
    """Il valore suggerito deve far atterrare la maturità ≈ 100%."""
    seg1 = ThermalSegment(hours=4, ambient_c=22,
                          container=Container.MASS_BOWL, environment=Environment.AMBIENT)
    seg2 = ThermalSegment(hours=20, ambient_c=4,
                          container=Container.MASS_BOX, environment=Environment.FRIDGE_HOME)
    curve = simulate_thermal([seg1, seg2], initial_c=24.0)
    pct = suggest_yeast_pct(curve, YeastKind.FRESH, target_work=24.0)
    res = simulate(curve, YeastKind.FRESH, yeast_pct=pct, target_work=24.0)
    assert abs(res.final_pct - 100.0) < 1.0
