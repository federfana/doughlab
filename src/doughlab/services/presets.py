"""Preset ricette: fasi + ingredienti di partenza per gli stili principali.

In futuro verranno uniti alle ricette salvate dall'utente in un'unica
barra "Ricette". Per adesso sono fissi.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .fermentation import DEFAULT_TARGET_WORK, YeastKind
from .ingredients import RecipeIngredients, RecipeStyle
from .scheduler import PhaseKind, PlanPhase
from .thermal import Container, Environment


@dataclass
class BakingAdvice:
    mode: str
    preheat_c: int
    preheat_minutes: int
    bake_c: int
    bake_minutes: float
    position: str
    note: str
    split_plate_c: int | None
    split_ceiling_c: int | None
    split_minutes: float | None
    split_hint: str


@dataclass
class Preset:
    key: str
    label: str
    style: RecipeStyle
    description: str
    flour_hint: str
    baking: BakingAdvice
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
        description="Impasto diretto: 62% idratazione, 2.8% sale, puntata e appretto a temperatura ambiente.",
        flour_hint="Farina per pizza di media forza, indicativamente 11,5-12,5% di proteine.",
        baking=BakingAdvice(
            mode="Forno domestico statico con pietra o acciaio",
            preheat_c=250,
            preheat_minutes=45,
            bake_c=250,
            bake_minutes=8,
            position="Ripiano medio-alto, sulla pietra o sull'acciaio",
            note="Valori orientativi: cuoci una pizza alla volta e controlla il cornicione verso fine cottura.",
            split_plate_c=420,
            split_ceiling_c=485,
            split_minutes=1.25,
            split_hint="Riferimento per napoletana ad alta temperatura: platea circa 380-430 °C, cielo circa 485 °C e 60-90 secondi. Valori orientativi: adatta il calore a condimento e forno.",
        ),
        ingredients=RecipeIngredients(
            panetto_g=250, n_panetti=4,
            hydration_pct=0.62, salt_pct=0.028, yeast_pct=0.0015,
        ),
        yeast_kind=YeastKind.FRESH,
        target_work=DEFAULT_TARGET_WORK,
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
        description="Puntata a temperatura ambiente, 20 ore in frigorifero e appretto finale.",
        flour_hint="Per la maturazione in frigo, orientativamente 12,5-13% di proteine.",
        baking=BakingAdvice(
            mode="Forno domestico statico con pietra o acciaio",
            preheat_c=250,
            preheat_minutes=45,
            bake_c=250,
            bake_minutes=8,
            position="Ripiano medio-alto, sulla pietra o sull'acciaio",
            note="Valori orientativi: cuoci una pizza alla volta e controlla il cornicione verso fine cottura.",
            split_plate_c=420,
            split_ceiling_c=485,
            split_minutes=1.25,
            split_hint="Riferimento per napoletana ad alta temperatura: platea circa 380-430 °C, cielo circa 485 °C e 60-90 secondi. Valori orientativi: adatta il calore a condimento e forno.",
        ),
        ingredients=RecipeIngredients(
            panetto_g=250, n_panetti=4,
            hydration_pct=0.65, salt_pct=0.028, yeast_pct=0.001,
        ),
        yeast_kind=YeastKind.FRESH,
        target_work=DEFAULT_TARGET_WORK,
        phases=[
            _phase(PhaseKind.MIX, "Impasto", 0.5, 22),
            _phase(PhaseKind.BULK, "Puntata", 2.0, 22),
            _phase(PhaseKind.MATURATION, "Maturazione in frigo", 20.0, 4,
                   Container.MASS_BOWL, Environment.FRIDGE_HOME),
            _phase(PhaseKind.TEMPER, "Cambio temperatura", 2.0, 22,
                   Container.MASS_BOWL),
            _phase(PhaseKind.SHAPE, "Staglio", 0.5, 22, Container.BALLS_BOX),
            _phase(PhaseKind.PROOF, "Appretto", 4.0, 22, Container.BALLS_BOX),
        ],
    ),
    Preset(
        key="teglia",
        label="Teglia romana 24h",
        style=RecipeStyle.TEGLIA,
        description="Idratazione 75%, olio 3% e maturazione in frigorifero.",
        flour_hint="Per 75% d'idratazione e maturazione in frigo, circa 13% di proteine è un punto di partenza ragionevole.",
        baking=BakingAdvice(
            mode="Forno domestico statico",
            preheat_c=250,
            preheat_minutes=30,
            bake_c=250,
            bake_minutes=16,
            position="Ripiano basso per la base, poi medio per dorare",
            note="La durata varia con spessore e condimento; controlla la base prima di sfornare.",
            split_plate_c=310,
            split_ceiling_c=200,
            split_minutes=10,
            split_hint="Riferimento per teglia: platea 300-320 °C, cielo circa 200 °C, 8-13 minuti. Partenza impostata a 310/200 °C per 10 minuti; controlla il fondo.",
        ),
        ingredients=RecipeIngredients(
            panetto_g=800, n_panetti=1,
            hydration_pct=0.75, salt_pct=0.025, yeast_pct=0.002,
            oil_pct=0.03,
        ),
        yeast_kind=YeastKind.FRESH,
        target_work=DEFAULT_TARGET_WORK,
        phases=[
            _phase(PhaseKind.MIX, "Impasto", 0.5, 22),
            _phase(PhaseKind.BULK, "Puntata", 2.0, 22),
            _phase(PhaseKind.MATURATION, "Maturazione in frigo", 24.0, 5,
                   Container.MASS_BOWL, Environment.FRIDGE_HOME),
            _phase(PhaseKind.TEMPER, "Cambio temperatura", 1.0, 22),
            _phase(PhaseKind.SHAPE, "Staglio", 0.5, 22, Container.BALLS_BOX),
            _phase(PhaseKind.PROOF, "Appretto", 3.5, 22, Container.BALLS_BOX),
            _phase(PhaseKind.OPEN, "Stesura e condimento", 1.0, 22, Container.BALLS_BOX),
        ],
    ),
    Preset(
        key="pinsa",
        label="Pinsa 48h",
        style=RecipeStyle.PINSA,
        description="Idratazione 80%, olio 2% e maturazione lunga in frigorifero.",
        flour_hint="Con 80% d'idratazione e 48 ore di maturazione, orientativamente 13-14% di proteine.",
        baking=BakingAdvice(
            mode="Forno domestico statico",
            preheat_c=250,
            preheat_minutes=30,
            bake_c=250,
            bake_minutes=8,
            position="Ripiano medio",
            note="Indicazione per la precottura: completa con il condimento secondo doratura e umidità dell'impasto.",
            split_plate_c=None,
            split_ceiling_c=None,
            split_minutes=None,
            split_hint="Non c'è un settaggio universale per la pinsa: inserisci i tuoi valori e registra l'esito per calibrare il profilo.",
        ),
        ingredients=RecipeIngredients(
            panetto_g=220, n_panetti=4,
            hydration_pct=0.80, salt_pct=0.025, yeast_pct=0.0012,
            oil_pct=0.02,
        ),
        yeast_kind=YeastKind.FRESH,
        target_work=DEFAULT_TARGET_WORK,
        phases=[
            _phase(PhaseKind.MIX, "Impasto", 0.5, 22),
            _phase(PhaseKind.BULK, "Puntata", 1.0, 22),
            _phase(PhaseKind.MATURATION, "Maturazione in frigo", 48.0, 4,
                   Container.MASS_BOWL, Environment.FRIDGE_HOME),
            _phase(PhaseKind.SHAPE, "Staglio", 0.5, 22, Container.BALLS_BOX),
            _phase(PhaseKind.PROOF, "Appretto", 3.0, 22, Container.BALLS_BOX),
            _phase(PhaseKind.OPEN, "Stesura", 0.5, 22, Container.BALLS_BOX),
        ],
    ),
    Preset(
        key="pane_biga",
        label="Pane 48h con biga",
        style=RecipeStyle.PANE,
        description="Biga al 30% della farina, 18 ore a 18 °C e maturazione successiva in frigorifero.",
        flour_hint="Per biga e maturazione lunga, orientativamente 12,5-13,5% di proteine.",
        baking=BakingAdvice(
            mode="Forno domestico statico con vapore iniziale",
            preheat_c=240,
            preheat_minutes=40,
            bake_c=220,
            bake_minutes=38,
            position="Ripiano centrale",
            note="Tempi orientativi per pagnotte da circa 500 g; il vapore aiuta lo sviluppo iniziale.",
            split_plate_c=None,
            split_ceiling_c=None,
            split_minutes=None,
            split_hint="Per il pane non c'è un profilo universale: imposta i tuoi valori in base a pezzatura e vapore e registra l'esito.",
        ),
        ingredients=RecipeIngredients(
            panetto_g=500, n_panetti=2,
            hydration_pct=0.70, salt_pct=0.022, yeast_pct=0.0012,
            preferment_pct=0.30, preferment_hydration_pct=0.45,
        ),
        yeast_kind=YeastKind.FRESH,
        target_work=DEFAULT_TARGET_WORK,
        phases=[
            _phase(PhaseKind.PREFERMENT, "Biga", 18.0, 18,
                   Container.MASS_BOWL, Environment.AMBIENT),
            _phase(PhaseKind.MIX, "Impasto", 0.5, 22),
            _phase(PhaseKind.BULK, "Puntata", 2.0, 22),
            _phase(PhaseKind.MATURATION, "Maturazione in frigo", 20.0, 5,
                   Container.MASS_BOWL, Environment.FRIDGE_HOME),
            _phase(PhaseKind.TEMPER, "Cambio temperatura", 2.0, 22),
            _phase(PhaseKind.SHAPE, "Formatura", 0.5, 22, Container.BALLS_BOX),
            _phase(PhaseKind.PROOF, "Appretto", 3.0, 22, Container.BALLS_BOX),
        ],
    ),
]


PRESETS_BY_KEY: dict[str, Preset] = {p.key: p for p in PRESETS}
