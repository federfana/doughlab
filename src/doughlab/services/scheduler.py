"""Scheduler: dalle fasi al piano completo (termico + fermentazione)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

import numpy as np

from .fermentation import DEFAULT_TARGET_WORK, FermentationResult, YeastKind
from .fermentation import simulate as simulate_fermentation
from .thermal import (
    Container,
    Environment,
    ThermalCurve,
    ThermalSegment,
)
from .thermal import (
    simulate as simulate_thermal,
)


class PhaseKind(StrEnum):
    PREFERMENT = "preferment"
    AUTOLYSE = "autolyse"
    MIX = "mix"
    BULK = "bulk"
    MATURATION = "maturation"
    TEMPER = "temper"
    SHAPE = "shape"
    PROOF = "proof"
    OPEN = "open"
    BAKE = "bake"


PHASE_LABELS: dict[PhaseKind, str] = {
    PhaseKind.PREFERMENT: "Prefermento (biga/poolish/LM)",
    PhaseKind.AUTOLYSE: "Autolisi",
    PhaseKind.MIX: "Impasto",
    PhaseKind.BULK: "Puntata",
    PhaseKind.MATURATION: "Maturazione",
    PhaseKind.TEMPER: "Cambio temperatura",
    PhaseKind.SHAPE: "Staglio",
    PhaseKind.PROOF: "Appretto",
    PhaseKind.OPEN: "Stesura",
    PhaseKind.BAKE: "Cottura",
}


FERMENTING_PHASES = set(PhaseKind) - {PhaseKind.AUTOLYSE, PhaseKind.BAKE}


@dataclass
class PlanPhase:
    kind: PhaseKind
    label: str
    hours: float
    ambient_c: float
    container: Container = Container.MASS_BOWL
    environment: Environment = Environment.AMBIENT


@dataclass
class PlanInput:
    start_at: datetime
    initial_dough_c: float
    phases: list[PlanPhase]
    yeast_kind: YeastKind
    yeast_pct: float
    target_work: float = DEFAULT_TARGET_WORK


@dataclass
class PhaseResult:
    phase: PlanPhase
    start_at: datetime
    end_at: datetime
    maturity_start_pct: float
    maturity_end_pct: float


@dataclass
class PlanResult:
    phases: list[PhaseResult]
    thermal: ThermalCurve
    fermentation: FermentationResult
    total_hours: float
    ready_at: datetime | None
    end_at: datetime


def _to_thermal_segments(phases: list[PlanPhase]) -> list[ThermalSegment]:
    return [
        ThermalSegment(
            hours=p.hours,
            ambient_c=p.ambient_c,
            container=p.container,
            environment=p.environment,
        )
        for p in phases
    ]


def fermentation_activity_mask(thermal: ThermalCurve, phases: list[PlanPhase]) -> np.ndarray:
    """Mark time intervals whose phase type allows yeast activity."""
    midpoints = 0.5 * (thermal.time_h[:-1] + thermal.time_h[1:])
    active = np.zeros(midpoints.shape, dtype=bool)
    cursor_h = 0.0
    for phase in phases:
        end_h = cursor_h + max(0.0, phase.hours)
        if phase.kind in FERMENTING_PHASES:
            active |= (midpoints >= cursor_h) & (midpoints < end_h)
        cursor_h = end_h
    return active


def build_plan(inp: PlanInput) -> PlanResult:
    thermal_segments = _to_thermal_segments(inp.phases)
    thermal = simulate_thermal(thermal_segments, initial_c=inp.initial_dough_c)
    active_mask = fermentation_activity_mask(thermal, inp.phases)

    # Per la fermentazione mascheriamo i tempi fuori dalle fasi fermentanti:
    # creiamo una curva "effettiva" dove durante autolisi/impasto/stesura/forno
    # il rate di lievito è trascurabile (0) tranne durante il forno dove è
    # letale e lo gestiremo come fine corsa (clamp a target).
    # Per MVP: integriamo sempre, ma segneremo le fasi non fermentanti.
    fermentation = simulate_fermentation(
        thermal,
        inp.yeast_kind,
        inp.yeast_pct,
        inp.target_work,
        active_mask=active_mask,
    )

    # Calcolo per fase: start/end datetime e maturity ai bordi.
    phases_out: list[PhaseResult] = []
    cursor_h = 0.0
    cursor_dt = inp.start_at
    time_h = thermal.time_h
    mat = fermentation.maturity_pct

    def interp_pct(h: float) -> float:
        if time_h.size == 0:
            return 0.0
        if h <= time_h[0]:
            return float(mat[0]) if mat.size else 0.0
        if h >= time_h[-1]:
            return float(mat[-1]) if mat.size else 0.0
        # numpy searchsorted + lerp
        i = int(time_h.searchsorted(h))
        t0, t1 = float(time_h[i - 1]), float(time_h[i])
        m0, m1 = float(mat[i - 1]), float(mat[i])
        return m0 + (h - t0) / (t1 - t0) * (m1 - m0) if t1 > t0 else m1

    for p in inp.phases:
        start_pct = interp_pct(cursor_h)
        end_h = cursor_h + p.hours
        end_dt = cursor_dt + timedelta(hours=p.hours)
        end_pct = interp_pct(end_h)
        phases_out.append(
            PhaseResult(
                phase=p,
                start_at=cursor_dt,
                end_at=end_dt,
                maturity_start_pct=start_pct,
                maturity_end_pct=end_pct,
            )
        )
        cursor_h = end_h
        cursor_dt = end_dt

    ready_at: datetime | None = None
    if fermentation.ready_at_h is not None:
        ready_at = inp.start_at + timedelta(hours=fermentation.ready_at_h)

    return PlanResult(
        phases=phases_out,
        thermal=thermal,
        fermentation=fermentation,
        total_hours=cursor_h,
        ready_at=ready_at,
        end_at=cursor_dt,
    )
