"""Modello termico dell'impasto.

Modello di Newton: dT/dt = -(T - T_amb) / τ

τ (ore) dipende dalla massa, dal contenitore e dal mezzo attorno.
Qui gestiamo profili tarabili per i casi tipici del panificatore
casalingo. Rispetto all'HTML del "piano di lavorazione" che usa due
τ fisse (2,8 h in frigo, 1,3 h fuori), distinguiamo:

- massa in puntata (contenitore grande, superficie/volume bassa)
- panetti stagliati (superficie/volume alta → risponde molto prima
  alla temperatura ambiente)
- frigo domestico vs cassetta chiusa vs cella controllata

I valori di default sono stime ragionevoli di partenza: possono
essere calibrate dai log reali in futuro con scipy.optimize.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np


class Container(StrEnum):
    MASS_BOWL = "mass_bowl"
    MASS_BOX = "mass_box"
    BALLS_BOX = "balls_box"
    BALLS_SINGLE = "balls_single"


class Environment(StrEnum):
    AMBIENT = "ambient"
    FRIDGE_HOME = "fridge_home"
    FRIDGE_BOX = "fridge_box"
    CHAMBER = "chamber"


CONTAINER_LABELS: dict[Container, str] = {
    Container.MASS_BOWL: "Massa in ciotola",
    Container.MASS_BOX: "Massa in cassetta coperta",
    Container.BALLS_BOX: "Panetti in cassetta",
    Container.BALLS_SINGLE: "Panetto singolo esposto",
}

ENVIRONMENT_LABELS: dict[Environment, str] = {
    Environment.AMBIENT: "Casa",
    Environment.FRIDGE_HOME: "Frigo",
    Environment.FRIDGE_BOX: "Frigo, cassetta chiusa",
    Environment.CHAMBER: "Cella",
}

# Scelte offerte nell'interfaccia; gli altri valori restano nel modello per i dati già salvati.
UI_CONTAINERS = (Container.MASS_BOWL, Container.BALLS_BOX)
UI_ENVIRONMENTS = (Environment.AMBIENT, Environment.FRIDGE_HOME, Environment.CHAMBER)
_LEGACY_CONTAINERS = {Container.MASS_BOX: Container.MASS_BOWL, Container.BALLS_SINGLE: Container.BALLS_BOX}
_LEGACY_ENVIRONMENTS = {Environment.FRIDGE_BOX: Environment.FRIDGE_HOME}


def parse_container(value: str) -> Container:
    """Contenitore ammesso dall'interfaccia; i valori ritirati diventano il più simile. `ValueError` se ignoto."""
    container = Container(value)
    return _LEGACY_CONTAINERS.get(container, container)


def parse_environment(value: str) -> Environment:
    environment = Environment(value)
    return _LEGACY_ENVIRONMENTS.get(environment, environment)


# τ in ore. Valori empirici di partenza da panificazione casalinga.
# chiave: (container, environment) -> tau_ore
TAU_TABLE: dict[tuple[Container, Environment], float] = {
    (Container.MASS_BOWL, Environment.AMBIENT): 1.6,
    (Container.MASS_BOWL, Environment.FRIDGE_HOME): 3.2,
    (Container.MASS_BOWL, Environment.FRIDGE_BOX): 4.0,
    (Container.MASS_BOWL, Environment.CHAMBER): 1.4,
    (Container.MASS_BOX, Environment.AMBIENT): 1.8,
    (Container.MASS_BOX, Environment.FRIDGE_HOME): 3.8,
    (Container.MASS_BOX, Environment.FRIDGE_BOX): 4.5,
    (Container.MASS_BOX, Environment.CHAMBER): 1.5,
    (Container.BALLS_BOX, Environment.AMBIENT): 0.9,
    (Container.BALLS_BOX, Environment.FRIDGE_HOME): 1.8,
    (Container.BALLS_BOX, Environment.FRIDGE_BOX): 2.3,
    (Container.BALLS_BOX, Environment.CHAMBER): 0.8,
    (Container.BALLS_SINGLE, Environment.AMBIENT): 0.5,
    (Container.BALLS_SINGLE, Environment.FRIDGE_HOME): 1.1,
    (Container.BALLS_SINGLE, Environment.FRIDGE_BOX): 1.4,
    (Container.BALLS_SINGLE, Environment.CHAMBER): 0.4,
}


def tau_for(container: Container, env: Environment) -> float:
    return TAU_TABLE[(container, env)]


@dataclass
class ThermalSegment:
    """Un segmento di tempo con contesto termico omogeneo."""

    hours: float
    ambient_c: float
    container: Container = Container.MASS_BOWL
    environment: Environment = Environment.AMBIENT
    tau_override: float | None = None

    @property
    def tau(self) -> float:
        return self.tau_override if self.tau_override is not None else tau_for(
            self.container, self.environment
        )


@dataclass
class ThermalCurve:
    time_h: np.ndarray
    temp_c: np.ndarray
    ambient_c: np.ndarray
    segment_index: np.ndarray = field(default_factory=lambda: np.array([]))


def simulate(
    segments: list[ThermalSegment],
    initial_c: float,
    step_h: float = 0.1,
) -> ThermalCurve:
    """Integra il modello di Newton segmento per segmento."""
    if not segments:
        return ThermalCurve(np.array([0.0]), np.array([initial_c]), np.array([initial_c]))

    times: list[float] = [0.0]
    temps: list[float] = [initial_c]
    ambs: list[float] = [segments[0].ambient_c]
    seg_idx: list[int] = [0]

    t = 0.0
    T = initial_c
    for i, seg in enumerate(segments):
        if seg.hours <= 0:
            continue
        end = t + seg.hours
        tau = seg.tau
        amb = seg.ambient_c
        # Soluzione esatta sul segmento: T(t+Δ) = T_amb + (T - T_amb) e^(-Δ/τ)
        while t < end - 1e-9:
            dt = min(step_h, end - t)
            T = amb + (T - amb) * np.exp(-dt / tau)
            t += dt
            times.append(t)
            temps.append(float(T))
            ambs.append(amb)
            seg_idx.append(i)

    return ThermalCurve(
        time_h=np.array(times),
        temp_c=np.array(temps),
        ambient_c=np.array(ambs),
        segment_index=np.array(seg_idx),
    )
