"""Modello di fermentazione — attività cumulata del lievito.

L'idea: integrare nel tempo il "rate" di attività k(T) del lievito,
che segue una legge tipo Q10 (approssimazione empirica dell'Arrhenius
nell'intervallo utile 2-35 °C):

    k(T) = k_ref * Q10 ^ ((T - T_ref) / 10)

Il "lavoro cumulato" W = ∫ k(T(t)) · [lievito%] dt è una grandezza
adimensionale che correla con la maturazione: raggiunto W_target
l'impasto è "pronto".

Parametri di default calibrati su esperienza panificatoria casalinga
(valori di Q10 ≈ 2.3-2.8 per il Saccharomyces cerevisiae industriale,
più bassi per lievito madre perché più tollerante al freddo).

Questi parametri sono tarabili: in futuro potremo calibrarli sui tuoi
log reali con una regressione.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from .thermal import ThermalCurve


class YeastKind(StrEnum):
    FRESH = "fresh"  # lievito di birra fresco
    DRY = "dry"  # lievito di birra secco (potenza ~3x il fresco)
    SOURDOUGH = "sourdough"  # lievito madre (licoli o solido)


@dataclass(frozen=True)
class YeastParams:
    """Parametri cinetici del lievito."""

    q10: float
    t_ref_c: float
    k_ref: float
    label: str


YEAST_PARAMS: dict[YeastKind, YeastParams] = {
    YeastKind.FRESH: YeastParams(q10=2.7, t_ref_c=25.0, k_ref=1.0, label="Lievito di birra fresco"),
    YeastKind.DRY: YeastParams(q10=2.7, t_ref_c=25.0, k_ref=3.0, label="Lievito di birra secco"),
    YeastKind.SOURDOUGH: YeastParams(
        q10=2.2, t_ref_c=26.0, k_ref=0.45, label="Lievito madre"
    ),
}


def rate(temp_c: float | np.ndarray, kind: YeastKind) -> float | np.ndarray:
    """Fattore di attività k(T) relativo al lievito scelto."""
    p = YEAST_PARAMS[kind]
    return p.k_ref * np.power(p.q10, (temp_c - p.t_ref_c) / 10.0)


@dataclass
class FermentationResult:
    time_h: np.ndarray
    rate: np.ndarray  # k(T(t))
    cumulative: np.ndarray  # W(t) = ∫ k·[lievito%] dt
    maturity_pct: np.ndarray  # W(t)/W_target * 100
    ready_at_h: float | None  # ora in cui raggiunge W_target
    final_pct: float


def simulate(
    curve: ThermalCurve,
    yeast_kind: YeastKind,
    yeast_pct: float,
    target_work: float = 24.0,
) -> FermentationResult:
    """Simula la maturazione lungo una curva termica.

    - `yeast_pct` è la percentuale di lievito sul peso farina.
    - `target_work` è il "lavoro" adimensionale al quale consideriamo
      la pasta matura. Default calibrato su una napoletana standard
      (~24 h di attività cumulata equivalenti a 24h a 25 °C con 1%
      di lievito fresco → prodotto nel modello = 24).

    I numeri assoluti vanno letti come indicativi: la cosa utile è il
    confronto fra scenari e la ricerca del lievito % ottimale.
    """
    if curve.time_h.size == 0:
        empty = np.array([])
        return FermentationResult(empty, empty, empty, empty, None, 0.0)

    k = np.asarray(rate(curve.temp_c, yeast_kind), dtype=float)
    integrand = k * yeast_pct
    # Integrale cumulativo con trapezi.
    dt = np.diff(curve.time_h)
    mid = 0.5 * (integrand[:-1] + integrand[1:])
    cum = np.concatenate([[0.0], np.cumsum(mid * dt)])

    maturity_pct = cum / target_work * 100.0

    ready_idx = int(np.searchsorted(cum, target_work))
    ready_at_h: float | None
    if 0 < ready_idx < cum.size:
        # Interpolazione lineare per precisione al minuto.
        t0, t1 = float(curve.time_h[ready_idx - 1]), float(curve.time_h[ready_idx])
        w0, w1 = float(cum[ready_idx - 1]), float(cum[ready_idx])
        ready_at_h = t0 + (target_work - w0) / (w1 - w0) * (t1 - t0) if w1 > w0 else t1
    else:
        ready_at_h = None

    return FermentationResult(
        time_h=curve.time_h,
        rate=k,
        cumulative=cum,
        maturity_pct=maturity_pct,
        ready_at_h=ready_at_h,
        final_pct=float(maturity_pct[-1]),
    )


def suggest_yeast_pct(
    curve: ThermalCurve,
    yeast_kind: YeastKind,
    target_work: float = 24.0,
) -> float:
    """Trova la percentuale di lievito che fa combaciare il piano con la maturità target."""
    unit = simulate(curve, yeast_kind, yeast_pct=1.0, target_work=target_work)
    final_work = unit.cumulative[-1] if unit.cumulative.size else 0.0
    if final_work <= 0:
        return 0.0
    return float(target_work / final_work)
