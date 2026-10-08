"""Strategie di lievitazione: scorciatoie (diretta, frigo...) che diventano le fasi del piano."""
from __future__ import annotations

from dataclasses import dataclass

from .scheduler import PhaseKind, PlanPhase
from .thermal import Container, Environment

DEFAULT_STRATEGY = "fridge_24"
BIGA_HOURS = 18.0
POOLISH_HOURS = 12.0
# Stesura finale prima della cottura, per stile.
OPEN_HOURS = {"teglia": 1.0, "pinsa": 0.5}


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
             bulk_h=2.0, fridge_h=17.5, shape_h=0.5, proof_h=4.0),
    Strategy("fridge_only_24", "Solo frigo 24 h", "Panetti formati subito e maturati in frigo, appretto breve.",
             bulk_h=1.0, fridge_h=20.5, shape_h=0.5, proof_h=2.0, balls_in_fridge=True),
    Strategy("fridge_48", "Frigo + ambiente 48 h", "Maturazione lunga della massa in frigo, più sapore e digeribilità.",
             bulk_h=2.0, fridge_h=42.0, shape_h=0.5, proof_h=3.5),
    Strategy("fridge_only_48", "Solo frigo 48 h", "Panetti in frigo per due giorni, appretto breve.",
             bulk_h=1.0, fridge_h=44.5, shape_h=0.5, proof_h=2.0, balls_in_fridge=True),
    Strategy("long_72", "Lunga 72 h", "Tre giorni di frigo: per impasti molto idratati, come la teglia.",
             bulk_h=1.0, fridge_h=66.0, shape_h=0.5, proof_h=4.5),
)
STRATEGIES_BY_KEY = {s.key: s for s in STRATEGIES}


def strategy_for(key: str) -> Strategy:
    return STRATEGIES_BY_KEY.get(key, STRATEGIES_BY_KEY[DEFAULT_STRATEGY])


def build_phases(
    key: str,
    room_c: float,
    fridge_c: float,
    *,
    preferment_hours: float = 0.0,
    preferment_label: str = "Prefermento",
    open_hours: float = 0.0,
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
    phases.append(phase(PhaseKind.BULK, "Puntata", s.bulk_h))
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
