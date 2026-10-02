"""Test del modello termico: proprietà fondamentali di Newton."""
from __future__ import annotations

import numpy as np

from doughlab.services.thermal import (
    Container,
    Environment,
    ThermalSegment,
    simulate,
    tau_for,
)


def test_tau_table_has_all_combos() -> None:
    for c in Container:
        for e in Environment:
            assert tau_for(c, e) > 0


def test_equilibrium_reaches_ambient() -> None:
    seg = ThermalSegment(hours=48, ambient_c=4.0, container=Container.MASS_BOX,
                         environment=Environment.FRIDGE_HOME)
    curve = simulate([seg], initial_c=24.0, step_h=0.1)
    assert abs(curve.temp_c[-1] - 4.0) < 0.5


def test_monotone_cooling() -> None:
    seg = ThermalSegment(hours=6, ambient_c=4.0, container=Container.MASS_BOWL,
                         environment=Environment.FRIDGE_HOME)
    curve = simulate([seg], initial_c=24.0, step_h=0.1)
    diffs = np.diff(curve.temp_c)
    assert (diffs <= 1e-6).all()


def test_monotone_warming() -> None:
    seg = ThermalSegment(hours=4, ambient_c=22.0, container=Container.BALLS_BOX,
                         environment=Environment.AMBIENT)
    curve = simulate([seg], initial_c=4.0, step_h=0.1)
    diffs = np.diff(curve.temp_c)
    assert (diffs >= -1e-6).all()


def test_balls_warm_faster_than_mass() -> None:
    """Rispetto a HTML allegato: panetti rispondono più in fretta della massa."""
    s_balls = ThermalSegment(hours=2, ambient_c=22, container=Container.BALLS_BOX,
                             environment=Environment.AMBIENT)
    s_mass = ThermalSegment(hours=2, ambient_c=22, container=Container.MASS_BOX,
                            environment=Environment.AMBIENT)
    c_balls = simulate([s_balls], initial_c=4.0)
    c_mass = simulate([s_mass], initial_c=4.0)
    assert c_balls.temp_c[-1] > c_mass.temp_c[-1]


def test_time_constant_matches_63pct() -> None:
    """A t=τ, la differenza con l'ambiente scende al 1/e ≈ 36.8%."""
    tau = tau_for(Container.MASS_BOWL, Environment.AMBIENT)
    seg = ThermalSegment(hours=tau, ambient_c=22,
                         container=Container.MASS_BOWL,
                         environment=Environment.AMBIENT)
    curve = simulate([seg], initial_c=4.0, step_h=0.01)
    expected = 22.0 + (4.0 - 22.0) * np.exp(-1.0)
    assert abs(curve.temp_c[-1] - expected) < 0.1
