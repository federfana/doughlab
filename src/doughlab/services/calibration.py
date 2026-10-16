"""Taratura del lievito sulle prove: quanto il tempo reale si discosta dalla stima, per ricetta."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from math import exp, log
from typing import Any

from .fields import parse_datetime

MIN_TRIALS = 2
# Una singola taratura non sposta il target oltre questo fattore (in più o in meno).
MAX_STEP = 1.5
# Sotto questo scarto relativo non si propone nulla.
MIN_CHANGE = 0.05
# Rapporti reale/stima fuori da questo intervallo sono quasi certamente errori di inserimento.
RATIO_RANGE = (0.25, 4.0)


@dataclass(frozen=True)
class Trial:
    predicted_h: float
    actual_h: float
    target_work: float  # target della versione con cui è stata fatta la prova


@dataclass(frozen=True)
class Calibration:
    trials: int
    mean_delta_h: float
    mean_ratio: float  # reale / stima, media geometrica
    current_target: float
    suggested_target: float | None


def trial_hours(
    plan: dict[str, Any] | None, started_at: datetime | None, ready_at: datetime | None
) -> tuple[float, float] | None:
    """(durata stimata, durata reale) in ore, se la prova le ha entrambe."""
    plan = plan or {}
    predicted = parse_datetime(plan.get("predicted_ready_at"))
    planned_start = parse_datetime(plan.get("started_at"))
    if not (predicted and planned_start and started_at and ready_at):
        return None
    predicted_h = (predicted - planned_start).total_seconds() / 3600
    actual_h = (ready_at - started_at).total_seconds() / 3600
    return (predicted_h, actual_h) if predicted_h > 0 and actual_h > 0 else None


def calibrate(trials: Sequence[Trial], current_target: float) -> Calibration | None:
    """Scarto medio e target consigliato.

    Il lievito è proporzionale al target: se con un target T il reale è durato r volte la stima, quel
    target avrebbe dovuto essere T·r. Il consiglio è la media geometrica di questi valori.
    """
    usable = [t for t in trials if RATIO_RANGE[0] <= t.actual_h / t.predicted_h <= RATIO_RANGE[1]]
    if not usable:
        return None
    ratios = [t.actual_h / t.predicted_h for t in usable]
    mean_ratio = exp(sum(log(r) for r in ratios) / len(ratios))
    mean_delta = sum(t.actual_h - t.predicted_h for t in usable) / len(usable)
    suggested: float | None = None
    if len(usable) >= MIN_TRIALS:
        ideal = exp(sum(log(t.target_work * r) for t, r in zip(usable, ratios, strict=True)) / len(usable))
        ideal = min(current_target * MAX_STEP, max(current_target / MAX_STEP, ideal))
        if abs(ideal / current_target - 1) >= MIN_CHANGE:
            suggested = round(ideal, 2)
    return Calibration(len(usable), mean_delta, mean_ratio, current_target, suggested)
