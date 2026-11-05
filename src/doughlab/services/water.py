"""Temperatura dell'acqua per ottenere la temperatura desiderata dell'impasto (formula del pizzaiolo)."""
from __future__ import annotations

from dataclasses import dataclass

# Di quanto l'impastare scalda l'impasto, in °C (di solito a mano si scalda appena, in planetaria qualche grado).
FRICTION_RISE_C = {"hand": 1.0, "planetary": 4.5, "mixer": 5.0}
DEFAULT_KNEADING = "hand"
DEFAULT_FLOUR_C = 20.0


# Oltre questi limiti l'acqua non è consigliabile: il lievito e il glutine soffrono sopra i 35 °C, e sotto
# i 4 °C (acqua del frigorifero) in casa si dovrebbe lavorare con il ghiaccio.
MAX_WATER_C = 35.0
MIN_WATER_C = 4.0


@dataclass(frozen=True)
class WaterAdvice:
    temperature_c: float  # quella da usare, entro i limiti
    formula: str
    message: str
    level: str  # "ok", "cold" (la formula chiedeva meno del minimo) o "hot" (chiedeva troppo)
    dough_c: float  # temperatura dell'impasto che si ottiene con quell'acqua
    wanted_c: float  # quella chiesta dalla formula, anche fuori dai limiti


def _comma(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def water_temperature(
    target_c: float,
    ambient_c: float,
    flour_c: float,
    kneading: str,
    preferment_c: float | None = None,
) -> WaterAdvice:
    """N × T impasto − (T ambiente + T farina [+ T prefermento] + fattore di attrito).

    N è il numero di temperature che si mediano (ambiente, farina, acqua ed eventuale prefermento): il
    fattore di attrito è N volte l'aumento di temperatura dovuto all'impasto, perché la formula lavora
    sulla somma e non sulla media.

    Se la formula chiede un'acqua oltre 35 °C (o sotto 4) si consiglia il limite e si dice a che
    temperatura uscirà l'impasto.
    """
    rise = FRICTION_RISE_C.get(kneading, FRICTION_RISE_C[DEFAULT_KNEADING])
    others = [ambient_c, flour_c]
    if preferment_c is not None:
        others.append(preferment_c)
    factors = len(others) + 1
    friction = round(rise * factors, 1)
    wanted = round(factors * target_c - sum(others) - friction, 1)
    value = min(MAX_WATER_C, max(MIN_WATER_C, wanted))
    dough = round((value + sum(others) + friction) / factors, 1)
    formula = f"{factors} × {target_c:g} − ({' + '.join(f'{x:g}' for x in [*others, friction])})"
    if wanted > MAX_WATER_C:
        level = "hot"
        message = (
            f"La formula chiederebbe {_comma(wanted)} °C, ma oltre {MAX_WATER_C:g} °C l'acqua danneggia lievito e glutine: "
            f"usane al massimo {MAX_WATER_C:g}. L'impasto uscirà a circa {_comma(dough)} °C; per arrivare a "
            f"{_comma(target_c)} °C scalda un po' la farina o l'ambiente."
        )
    elif wanted < MIN_WATER_C:
        level = "cold"
        message = (
            f"La formula chiederebbe {_comma(wanted)} °C, ma sotto i {MIN_WATER_C:g} °C (acqua del frigorifero) è "
            f"un'acqua quasi ghiacciata: usa {MIN_WATER_C:g} °C. L'impasto uscirà a circa {_comma(dough)} °C; per "
            f"arrivare a {_comma(target_c)} °C raffredda la farina, impasta nelle ore fresche o alza la T° desiderata."
        )
    elif value > 25:
        level, message = "ok", "Acqua tiepida: l'ambiente o la farina sono freddi rispetto all'impasto."
    elif value >= 10:
        level, message = "ok", "Acqua a temperatura ambiente, dal rubinetto."
    else:
        level, message = "ok", "Acqua fredda, dal frigorifero."
    return WaterAdvice(value, formula, message, level, dough, wanted)
