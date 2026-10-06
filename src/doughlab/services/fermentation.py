"""Modello di fermentazione — attività cumulata del lievito.

L'idea: integrare nel tempo il "rate" di attività k(T) del lievito,
che segue una legge tipo Q10 (approssimazione empirica dell'Arrhenius
nell'intervallo utile 2-35 °C):

    k(T) = k_ref * Q10 ^ ((T - T_ref) / 10)

Il "lavoro cumulato" W = ∫ k(T(t)) · [lievito%] dt è una grandezza
adimensionale che correla con la maturazione: raggiunto W_target
l'impasto è "pronto".

Fresco e secco attivo sono tarati su dosi pubblicate da calcolatori
indipendenti (PizzApp, Dough School, when.pizza): Q10 ≈ 3.0 (regola di
Hamelman, x3 ogni 9 °C). Il lievito madre non ha riferimenti ed è invariato.

I parametri restano tarabili: in futuro potremo calibrarli sui tuoi
log reali con una regressione.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from .thermal import ThermalCurve

DEFAULT_TARGET_WORK = 1.0


class YeastKind(StrEnum):
    FRESH = "fresh"  # lievito di birra fresco
    DRY = "dry"  # lievito di birra secco attivo (potenza ~2.4x il fresco)
    SOURDOUGH = "sourdough"  # lievito madre (licoli o solido)


@dataclass(frozen=True)
class YeastParams:
    """Parametri cinetici del lievito."""

    q10: float
    t_ref_c: float
    k_ref: float
    label: str


YEAST_PARAMS: dict[YeastKind, YeastParams] = {
    YeastKind.FRESH: YeastParams(q10=3.0, t_ref_c=25.0, k_ref=0.56, label="Lievito di birra fresco"),
    # Secco attivo = 1/2.4 del peso del fresco (conversioni di Yeasto, when.pizza, mypizzanight).
    YeastKind.DRY: YeastParams(q10=3.0, t_ref_c=25.0, k_ref=0.56 * 2.4, label="Lievito di birra secco attivo"),
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
    target_work: float = DEFAULT_TARGET_WORK,
    active_mask: np.ndarray | None = None,
) -> FermentationResult:
    """Simula la maturazione lungo una curva termica.

        - `yeast_pct` è la percentuale sul peso farina come frazione
            (0.0015 = 0.15%).
        - `target_work` usa punti percentuali lievito per ora: il fattore
            100 converte la frazione in punti percentuali. Il target predefinito
            è un riferimento iniziale, da calibrare con prove reali.

    I numeri assoluti vanno letti come indicativi: la cosa utile è il
    confronto fra scenari e la ricerca del lievito % ottimale.
    """
    if curve.time_h.size == 0:
        empty = np.array([])
        return FermentationResult(empty, empty, empty, empty, None, 0.0)

    k = np.asarray(rate(curve.temp_c, yeast_kind), dtype=float)
    integrand = k * yeast_pct * 100.0
    # Integrale cumulativo con trapezi.
    dt = np.diff(curve.time_h)
    mid = 0.5 * (integrand[:-1] + integrand[1:])
    if active_mask is not None:
        if active_mask.shape != dt.shape:
            raise ValueError("active_mask must have one value per time interval")
        mid = np.where(active_mask, mid, 0.0)
    cum = np.concatenate([[0.0], np.cumsum(mid * dt)])

    maturity_pct = cum / target_work * 100.0

    ready_at_h: float | None
    reached_target = cum[-1] >= target_work or np.isclose(
        cum[-1], target_work, rtol=1e-12, atol=1e-12
    )
    if reached_target:
        search_target = min(target_work, float(cum[-1]))
        ready_idx = int(np.searchsorted(cum, search_target))
        if ready_idx >= cum.size:
            ready_at_h = float(curve.time_h[-1])
        elif ready_idx == 0:
            ready_at_h = float(curve.time_h[0])
        else:
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
    target_work: float = DEFAULT_TARGET_WORK,
    active_mask: np.ndarray | None = None,
) -> float:
    """Trova la frazione di lievito che fa combaciare il piano col target."""
    reference_pct = 0.01
    reference = simulate(
        curve,
        yeast_kind,
        yeast_pct=reference_pct,
        target_work=target_work,
        active_mask=active_mask,
    )
    reference_work = reference.cumulative[-1] if reference.cumulative.size else 0.0
    if reference_work <= 0:
        return 0.0
    return float(reference_pct * target_work / reference_work)
