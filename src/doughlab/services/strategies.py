"""Strategie di lievitazione: scorciatoie (diretta, frigo...) che diventano le fasi del piano."""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, replace

from .scheduler import PhaseKind, PlanPhase
from .thermal import Container, Environment

DEFAULT_STRATEGY = "fridge_24"
BIGA_HOURS = 18.0
POOLISH_HOURS = 12.0
# Stesura finale prima della cottura, per stile.
OPEN_HOURS = {"teglia": 1.0, "pinsa": 0.5}


# Impasto a mano o in planetaria: il glutine si rinforza con le pieghe durante la puntata.
FOLD_KNEADING = frozenset({"hand", "planetary"})
# Pause prima di ogni piega (30, 20, 15 min dopo l'impasto o la piega precedente) e durata della piega.
FOLD_REST_H = (30 / 60, 20 / 60, 15 / 60)
FOLD_HOURS = 5 / 60
MIN_BULK_AFTER_FOLDS_H = 0.25


@dataclass(frozen=True)
class Strategy:
    key: str
    label: str
    description: str
    bulk_h: float
    fridge_h: float
    shape_h: float
    proof_h: float
    # Panetti formati prima del frigo (maturazione "solo frigo") invece della massa.
    balls_in_fridge: bool = False
    # Temperatura consigliata dell'impasto a fine impasto: più bassa se matura a lungo in frigo.
    dough_c: float = 24.0

    @property
    def total_h(self) -> float:
        return self.bulk_h + self.fridge_h + self.shape_h + self.proof_h

    @property
    def ambient_h(self) -> float:
        return self.total_h - self.fridge_h


STRATEGIES: tuple[Strategy, ...] = (
    Strategy("direct_8", "Diretta 8 h", "Tutto a temperatura ambiente, in giornata.",
             bulk_h=2.0, fridge_h=0.0, shape_h=0.5, proof_h=5.5),
    Strategy("fridge_24", "Frigo + ambiente 24 h", "Massa in frigo, appretto dei panetti a temperatura ambiente.",
             bulk_h=2.0, fridge_h=17.5, shape_h=0.5, proof_h=4.0, dough_c=21.0),
    Strategy("fridge_only_24", "Solo frigo 24 h", "Panetti formati subito e maturati in frigo, appretto breve.",
             bulk_h=1.0, fridge_h=20.5, shape_h=0.5, proof_h=2.0, balls_in_fridge=True, dough_c=21.0),
    Strategy("fridge_48", "Frigo + ambiente 48 h", "Maturazione lunga della massa in frigo, più sapore e digeribilità.",
             bulk_h=2.0, fridge_h=42.0, shape_h=0.5, proof_h=3.5, dough_c=20.0),
    Strategy("fridge_only_48", "Solo frigo 48 h", "Panetti in frigo per due giorni, appretto breve.",
             bulk_h=1.0, fridge_h=44.5, shape_h=0.5, proof_h=2.0, balls_in_fridge=True, dough_c=20.0),
    Strategy("long_72", "Lunga 72 h", "Tre giorni di frigo: per impasti molto idratati, come la teglia.",
             bulk_h=1.0, fridge_h=66.0, shape_h=0.5, proof_h=4.5, dough_c=20.0),
)
STRATEGIES_BY_KEY = {s.key: s for s in STRATEGIES}


def strategy_for(key: str) -> Strategy:
    return STRATEGIES_BY_KEY.get(key, STRATEGIES_BY_KEY[DEFAULT_STRATEGY])


# Più acqua nell'impasto = impasto più molle e più veloce a lievitare: si parte più freddi.
HYDRATION_REF = 0.65
COOLER_PER_5_PCT_C = 1.0
MAX_COOLER_C = 3.0
MIN_DOUGH_C = 18.0


def suggested_dough_c(key: str, hydration: float) -> float:
    """T° impasto consigliata: quella della strategia, 1 °C più fredda ogni 5 punti di idratazione sopra il 65%."""
    cooler = min(MAX_COOLER_C, max(0.0, (hydration - HYDRATION_REF) * 100 / 5 * COOLER_PER_5_PCT_C))
    return max(MIN_DOUGH_C, math.floor((strategy_for(key).dough_c - cooler) * 2 + 0.5) / 2)


def _bulk_phases(make: Callable[..., PlanPhase], bulk_h: float, folds: bool) -> list[PlanPhase]:
    """Puntata con le pieghe di rinforzo (fino a 3, quante ne stanno lasciando un po' di puntata dopo)."""
    steps: list[tuple[float, float]] = []
    used_h = 0.0
    for rest_h in FOLD_REST_H if folds else ():
        if used_h + rest_h + FOLD_HOURS + MIN_BULK_AFTER_FOLDS_H > bulk_h + 1e-9:
            break
        steps.append((rest_h, FOLD_HOURS))
        used_h += rest_h + FOLD_HOURS
    if not steps:
        return [make(PhaseKind.BULK, "Puntata", bulk_h)]
    phases: list[PlanPhase] = []
    for i, (rest_h, fold_h) in enumerate(steps, start=1):
        phases.append(make(PhaseKind.BULK, "Puntata", rest_h))
        phases.append(make(PhaseKind.FOLD, f"Piega di rinforzo {i}/{len(steps)}", fold_h))
    phases.append(make(PhaseKind.BULK, "Puntata", bulk_h - used_h))
    return phases


def with_folds(phases: list[PlanPhase], enabled: bool) -> list[PlanPhase]:
    """Aggiunge le pieghe alla prima puntata, o le toglie restituendo il loro tempo alla puntata."""
    has_folds = any(p.kind == PhaseKind.FOLD for p in phases)
    if enabled and has_folds or not enabled and not has_folds:
        return list(phases)
    result: list[PlanPhase] = []
    if enabled:
        done = False
        for p in phases:
            if p.kind == PhaseKind.BULK and not done:
                done = True
                result += _bulk_phases(
                    lambda kind, label, hours, p=p: replace(p, kind=kind, label=label, hours=hours),
                    p.hours, True,
                )
            else:
                result.append(p)
        return result
    merge_next = False
    for p in phases:
        if p.kind == PhaseKind.FOLD:
            if result and result[-1].kind == PhaseKind.BULK:
                result[-1] = replace(result[-1], hours=result[-1].hours + p.hours)
            merge_next = True
        elif p.kind == PhaseKind.BULK and merge_next and result and result[-1].kind == PhaseKind.BULK:
            result[-1] = replace(result[-1], hours=result[-1].hours + p.hours)
            merge_next = False
        else:
            result.append(p)
            merge_next = False
    return result


def build_phases(
    key: str,
    room_c: float,
    fridge_c: float,
    *,
    preferment_hours: float = 0.0,
    preferment_label: str = "Prefermento",
    open_hours: float = 0.0,
    folds: bool = False,
) -> list[PlanPhase]:
    """Fasi di una strategia con le temperature scelte: ambiente `room_c`, frigo `fridge_c`."""
    s = strategy_for(key)

    def phase(kind: PhaseKind, label: str, hours: float, *, cold: bool = False,
              balls: bool = False) -> PlanPhase:
        return PlanPhase(
            kind=kind, label=label, hours=hours,
            ambient_c=fridge_c if cold else room_c,
            container=Container.BALLS_BOX if balls else Container.MASS_BOWL,
            environment=Environment.FRIDGE_HOME if cold else Environment.AMBIENT,
        )

    phases: list[PlanPhase] = []
    if preferment_hours > 0:
        phases.append(phase(PhaseKind.PREFERMENT, preferment_label, preferment_hours))
    phases.append(phase(PhaseKind.MIX, "Impasto", 0.5))
    phases += _bulk_phases(phase, s.bulk_h, folds)
    shape = phase(PhaseKind.SHAPE, "Staglio", s.shape_h, balls=True)
    fridge = phase(PhaseKind.MATURATION, "Maturazione in frigo", s.fridge_h, cold=True,
                   balls=s.balls_in_fridge)
    if s.fridge_h > 0 and s.balls_in_fridge:
        phases += [shape, fridge]
    elif s.fridge_h > 0:
        phases += [fridge, shape]
    else:
        phases.append(shape)
    phases.append(phase(PhaseKind.PROOF, "Appretto", s.proof_h, balls=True))
    if open_hours > 0:
        phases.append(phase(PhaseKind.OPEN, "Stesura", open_hours, balls=True))
    return phases
