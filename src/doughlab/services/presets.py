"""Preset ricette: fasi + ingredienti di partenza per gli stili principali.

In futuro verranno uniti alle ricette salvate dall'utente in un'unica
barra "Ricette". Per adesso sono fissi.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .fermentation import YeastKind
from .ingredients import RecipeIngredients, RecipeStyle
from .scheduler import PhaseKind, PlanPhase
from .thermal import Container, Environment


@dataclass
class Preset:
    key: str
    label: str
    style: RecipeStyle
    ingredients: RecipeIngredients
    yeast_kind: YeastKind
    target_work: float
    phases: list[PlanPhase] = field(default_factory=list)


def _phase(kind: PhaseKind, label: str, hours: float, amb: float,
           c: Container = Container.MASS_BOWL,
           e: Environment = Environment.AMBIENT) -> PlanPhase:
    return PlanPhase(kind=kind, label=label, hours=hours, ambient_c=amb,
                     container=c, environment=e)


PRESETS: list[Preset] = [
    Preset(
        key="napoletana",
        label="Napoletana",
        style=RecipeStyle.NAPOLETANA,
        ingredients=RecipeIngredients(
            panetto_g=250, n_panetti=4,
            hydration_pct=0.62, salt_pct=0.028, yeast_pct=0.0015,
        ),
        yeast_kind=YeastKind.FRESH,
        target_work=24.0,
        phases=[
            _phase(PhaseKind.MIX, "Impasto", 0.5, 22),
            _phase(PhaseKind.BULK, "Puntata", 2.0, 22),
            _phase(PhaseKind.SHAPE, "Staglio", 0.5, 22, Container.BALLS_BOX),
            _phase(PhaseKind.PROOF, "Appretto", 6.0, 22, Container.BALLS_BOX),
        ],
    ),
    Preset(
        key="napoletana_frigo",
        label="Napoletana 24h frigo",
        style=RecipeStyle.NAPOLETANA,
        ingredients=RecipeIngredients(
            panetto_g=250, n_panetti=4,
            hydration_pct=0.65, salt_pct=0.028, yeast_pct=0.001,
        ),
        yeast_kind=YeastKind.FRESH,
        target_work=24.0,
        phases=[
            _phase(PhaseKind.MIX, "Impasto", 0.5, 22),
            _phase(PhaseKind.BULK, "Puntata", 2.0, 22),
            _phase(PhaseKind.MATURATION, "Maturazione in frigo", 20.0, 4,
                   Container.MASS_BOX, Environment.FRIDGE_HOME),
            _phase(PhaseKind.TEMPER, "Cambio temperatura", 2.0, 22,
                   Container.MASS_BOX),
            _phase(PhaseKind.SHAPE, "Staglio", 0.5, 22, Container.BALLS_BOX),
            _phase(PhaseKind.PROOF, "Appretto", 4.0, 22, Container.BALLS_BOX),
        ],
    ),
    Preset(
        key="teglia",
        label="Teglia romana 24h",
        style=RecipeStyle.TEGLIA,
        ingredients=RecipeIngredients(
            panetto_g=800, n_panetti=1,
            hydration_pct=0.75, salt_pct=0.025, yeast_pct=0.002,
            oil_pct=0.03,
        ),
        yeast_kind=YeastKind.FRESH,
        target_work=24.0,
        phases=[
            _phase(PhaseKind.MIX, "Impasto", 0.5, 22),
            _phase(PhaseKind.BULK, "Puntata", 2.0, 22),
            _phase(PhaseKind.MATURATION, "Maturazione in frigo", 24.0, 5,
                   Container.MASS_BOX, Environment.FRIDGE_HOME),
            _phase(PhaseKind.TEMPER, "Cambio temperatura", 1.0, 22),
            _phase(PhaseKind.SHAPE, "Staglio", 0.5, 22, Container.BALLS_BOX),
            _phase(PhaseKind.PROOF, "Appretto", 3.5, 22, Container.BALLS_BOX),
            _phase(PhaseKind.OPEN, "Stesura e condimento", 1.0, 22),
        ],
    ),
    Preset(
        key="pinsa",
        label="Pinsa 48h",
        style=RecipeStyle.PINSA,
        ingredients=RecipeIngredients(
            panetto_g=220, n_panetti=4,
            hydration_pct=0.80, salt_pct=0.025, yeast_pct=0.0012,
            oil_pct=0.02,
        ),
        yeast_kind=YeastKind.FRESH,
        target_work=24.0,
        phases=[
            _phase(PhaseKind.MIX, "Impasto", 0.5, 22),
            _phase(PhaseKind.BULK, "Puntata", 1.0, 22),
            _phase(PhaseKind.MATURATION, "Maturazione in frigo", 48.0, 4,
                   Container.MASS_BOX, Environment.FRIDGE_HOME),
            _phase(PhaseKind.SHAPE, "Staglio", 0.5, 22, Container.BALLS_BOX),
            _phase(PhaseKind.PROOF, "Appretto", 3.0, 22, Container.BALLS_BOX),
            _phase(PhaseKind.OPEN, "Stesura", 0.5, 22),
        ],
    ),
    Preset(
        key="pane_biga",
        label="Pane 48h con biga",
        style=RecipeStyle.PANE,
        ingredients=RecipeIngredients(
            panetto_g=500, n_panetti=2,
            hydration_pct=0.70, salt_pct=0.022, yeast_pct=0.0012,
            preferment_pct=0.30, preferment_hydration_pct=0.45,
        ),
        yeast_kind=YeastKind.FRESH,
        target_work=28.0,
        phases=[
            _phase(PhaseKind.PREFERMENT, "Biga", 18.0, 18,
                   Container.MASS_BOX, Environment.AMBIENT),
            _phase(PhaseKind.MIX, "Impasto", 0.5, 22),
            _phase(PhaseKind.BULK, "Puntata", 2.0, 22),
            _phase(PhaseKind.MATURATION, "Maturazione in frigo", 20.0, 5,
                   Container.MASS_BOX, Environment.FRIDGE_HOME),
            _phase(PhaseKind.TEMPER, "Cambio temperatura", 2.0, 22),
            _phase(PhaseKind.SHAPE, "Formatura", 0.5, 22, Container.BALLS_BOX),
            _phase(PhaseKind.PROOF, "Appretto", 3.0, 22, Container.BALLS_BOX),
        ],
    ),
]


PRESETS_BY_KEY: dict[str, Preset] = {p.key: p for p in PRESETS}
