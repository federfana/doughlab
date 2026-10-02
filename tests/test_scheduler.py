"""Test dello scheduler end-to-end."""
from __future__ import annotations

from datetime import datetime

from doughlab.services.fermentation import YeastKind
from doughlab.services.scheduler import PhaseKind, PlanInput, PlanPhase, build_plan
from doughlab.services.thermal import Container, Environment


def _napoletana_phases() -> list[PlanPhase]:
    return [
        PlanPhase(PhaseKind.MIX, "Impasto", 0.5, 22, Container.MASS_BOWL, Environment.AMBIENT),
        PlanPhase(PhaseKind.BULK, "Puntata", 2.0, 22, Container.MASS_BOWL, Environment.AMBIENT),
        PlanPhase(PhaseKind.SHAPE, "Staglio", 0.5, 22, Container.BALLS_BOX, Environment.AMBIENT),
        PlanPhase(PhaseKind.PROOF, "Appretto", 6.0, 22, Container.BALLS_BOX, Environment.AMBIENT),
    ]


def test_total_hours_sum() -> None:
    plan = build_plan(
        PlanInput(
            start_at=datetime(2026, 10, 3, 11, 0),
            initial_dough_c=24,
            phases=_napoletana_phases(),
            yeast_kind=YeastKind.FRESH,
            yeast_pct=0.3,
            target_work=24,
        )
    )
    assert abs(plan.total_hours - 9.0) < 1e-6
    assert plan.end_at.hour == 20


def test_end_and_phase_consistency() -> None:
    plan = build_plan(
        PlanInput(
            start_at=datetime(2026, 10, 3, 11, 0),
            initial_dough_c=24,
            phases=_napoletana_phases(),
            yeast_kind=YeastKind.FRESH,
            yeast_pct=0.3,
            target_work=24,
        )
    )
    assert plan.phases[0].start_at == datetime(2026, 10, 3, 11, 0)
    assert plan.phases[-1].end_at == plan.end_at


def test_maturity_increases_in_fermenting_phases() -> None:
    plan = build_plan(
        PlanInput(
            start_at=datetime(2026, 10, 3, 11, 0),
            initial_dough_c=24,
            phases=_napoletana_phases(),
            yeast_kind=YeastKind.FRESH,
            yeast_pct=0.3,
            target_work=24,
        )
    )
    # L'ultima fase (appretto) deve mostrare un incremento positivo di maturità.
    last = plan.phases[-1]
    assert last.maturity_end_pct > last.maturity_start_pct
