"""Risorse web condivise: template Jinja e contesto comune a tutte le pagine."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import Path as PathParam
from fastapi.templating import Jinja2Templates

from .config import settings
from .services.fermentation import YEAST_PARAMS, YeastKind
from .services.fields import format_hours, format_minutes
from .services.ingredients import STYLE_LABELS, RecipeStyle
from .services.presets import PRESETS
from .services.scheduler import PHASE_LABELS, PhaseKind
from .services.strategies import STRATEGIES
from .services.thermal import (
    CONTAINER_LABELS,
    ENVIRONMENT_LABELS,
    UI_CONTAINERS,
    UI_ENVIRONMENTS,
    Container,
    Environment,
)

STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"
WEEKDAYS_IT = ("lun", "mar", "mer", "gio", "ven", "sab", "dom")
MONTHS_IT = (
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
)
YEAST_SHORT_LABELS = {
    YeastKind.FRESH: "Fresco",
    YeastKind.DRY: "Secco",
    YeastKind.SOURDOUGH: "Madre",
}
CONTAINER_ICONS = {
    Container.MASS_BOWL: "🥣",
    Container.MASS_BOX: "📦",
    Container.BALLS_BOX: "📦",
    Container.BALLS_SINGLE: "🥣",
}
ENVIRONMENT_ICONS = {
    Environment.AMBIENT: "🏠",
    Environment.FRIDGE_HOME: "❄️",
    Environment.FRIDGE_BOX: "❄️",
    Environment.CHAMBER: "🌡️",
}

templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.filters["hours"] = format_hours
templates.env.filters["minutes"] = format_minutes

# Identificativi nei percorsi: oltre i 64 bit SQLite solleva OverflowError.
RowId = Annotated[int, PathParam(ge=1, le=2_147_483_647)]


def common_ctx() -> dict[str, Any]:
    """Dropdown + metadati sempre serviti al template."""
    return {
        "app_name": settings.app_name,
        "yeast_kinds": [
            (k.value, YEAST_SHORT_LABELS[k], YEAST_PARAMS[k].label) for k in YeastKind
        ],
        "phase_kinds": [(k.value, PHASE_LABELS[k]) for k in PhaseKind],
        "containers": [(c.value, CONTAINER_LABELS[c], CONTAINER_ICONS[c]) for c in UI_CONTAINERS],
        "environments": [
            (e.value, ENVIRONMENT_LABELS[e], ENVIRONMENT_ICONS[e]) for e in UI_ENVIRONMENTS
        ],
        "styles": [(s.value, STYLE_LABELS[s]) for s in RecipeStyle],
        "strategies": STRATEGIES,
        "presets": [
            {
                "key": p.key,
                "label": p.label,
                "style": p.style.value,
                "description": p.description,
                "flour_hint": p.flour_hint,
            }
            for p in PRESETS
        ],
        "weekdays_it": WEEKDAYS_IT,
        "months_it": MONTHS_IT,
    }
