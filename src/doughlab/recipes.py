"""Ricette salvate con versioning: ogni salvataggio con lo stesso nome è una nuova versione."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .db import SessionLocal
from .models import DiaryEntry, Recipe, RecipeVersion
from .planning import default_recipe_ctx, number, parse_ingredients, parse_phase_form, preset_ctx
from .services.fermentation import DEFAULT_TARGET_WORK, YeastKind
from .services.flour_blend import parse_rows
from .services.ingredients import STYLE_LABELS, RecipeIngredients, RecipeStyle
from .services.presets import PRESETS_BY_KEY
from .services.thermal import parse_container, parse_environment
from .web import RowId, common_ctx, templates

router = APIRouter(prefix="/ricette")

MAX_NAME = 80
MAX_MESSAGE = 200
MAX_RECIPES = 500


def payload_from_form(data: dict[str, str]) -> dict[str, Any]:
    """Quello che definisce la ricetta: formula, fasi, lievito e forno (non l'orario di partenza)."""
    try:
        yeast_kind = YeastKind(data.get("yeast_kind", "")).value
    except ValueError:
        yeast_kind = YeastKind.FRESH.value
    oven = data.get("oven_profile", "split")
    ingredients = parse_ingredients(data)
    return {
        "preset_key": data.get("preset_key", ""),
        "yeast_kind": yeast_kind,
        "target_work": number(data, "target_work", DEFAULT_TARGET_WORK, 0.01, 100),
        "oven_profile": oven if oven in {"home", "split"} else "split",
        "initial_dough_c": number(data, "initial_dough_c", 24, 0, 40),
        "ingredients": {
            "panetto_g": ingredients.panetto_g,
            "n_panetti": ingredients.n_panetti,
            "hydration_pct": ingredients.hydration_pct,
            "salt_pct": ingredients.salt_pct,
            "oil_pct": ingredients.oil_pct,
            "sugar_pct": ingredients.sugar_pct,
            "preferment_pct": ingredients.preferment_pct,
            "preferment_hydration_pct": ingredients.preferment_hydration_pct,
            "preferment_yeast_share": ingredients.preferment_yeast_share,
        },
        "phases": [
            {
                "kind": phase.kind.value,
                "label": phase.label,
                "hours": phase.hours,
                "ambient_c": phase.ambient_c,
                "container": phase.container.value,
                "environment": phase.environment.value,
            }
            for phase in parse_phase_form(data)
        ],
        "flours": [{"id": flour_id, "pct": pct} for flour_id, pct in parse_rows(data)],
    }


def _recipe_ctx(recipe: Recipe, version: RecipeVersion) -> dict[str, Any] | None:
    """Contesto del pianificatore per una versione salvata; None se il payload è illeggibile."""
    payload = version.payload
    try:
        base = preset_ctx(str(payload.get("preset_key", ""))) or default_recipe_ctx()
        ingredients = RecipeIngredients(yeast_pct=0.0, **payload["ingredients"])
        phases = [
            {
                **{key: phase[key] for key in ("kind", "label", "hours", "ambient_c")},
                "container": parse_container(phase["container"]).value,
                "environment": parse_environment(phase["environment"]).value,
            }
            for phase in payload["phases"]
        ]
        base.update(
            recipe_name=recipe.name,
            yeast_kind=YeastKind(payload["yeast_kind"]).value,
            target_work=float(payload["target_work"]),
            oven_profile=payload["oven_profile"],
            initial_dough_c=float(payload["initial_dough_c"]),
            ingredients=asdict(ingredients),
            phases=phases,
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if not phases:
        return None
    base["flour_rows"] = [
        (item["id"], float(item["pct"]))
        for item in payload.get("flours", [])
        if isinstance(item, dict) and isinstance(item.get("id"), int) and isinstance(item.get("pct"), (int, float))
    ][:3]
    return base


async def load_recipe(recipe_id: int, version: int | None = None) -> dict[str, Any] | None:
    """Pianificatore precompilato con la ricetta salvata (ultima versione se non indicata)."""
    async with SessionLocal() as session:
        recipe = await session.get(Recipe, recipe_id, options=[selectinload(Recipe.versions)])
        if recipe is None or not recipe.versions:
            return None
        chosen = next((v for v in recipe.versions if v.version == version), recipe.versions[0])
        context = _recipe_ctx(recipe, chosen)
        if context is None:
            return None
        context["saved_recipe"] = {"id": recipe.id, "name": recipe.name, "version": chosen.version}
        return context


async def panel_context(
    message: str | None = None,
    error: str | None = None,
    saved: dict[str, Any] | None = None,
    loaded: dict[str, Any] | None = None,
) -> dict[str, Any]:
    async with SessionLocal() as session:
        recipes = (
            await session.scalars(
                select(Recipe).options(selectinload(Recipe.versions)).order_by(Recipe.name).limit(MAX_RECIPES)
            )
        ).all()
        plans = (await session.scalars(select(DiaryEntry.plan))).all()
    trials: dict[int, int] = {}
    for plan in plans:
        recipe_id = plan.get("recipe_id") if isinstance(plan, dict) else None
        if isinstance(recipe_id, int):
            trials[recipe_id] = trials.get(recipe_id, 0) + 1
    items = [
        {
            "id": recipe.id,
            "name": recipe.name,
            "style": STYLE_LABELS.get(RecipeStyle(recipe.style), "") if recipe.style in RecipeStyle else "",
            "versions": [
                {"version": v.version, "message": v.message, "created_at": v.created_at}
                for v in recipe.versions
            ],
            "trials": trials.get(recipe.id, 0),
        }
        for recipe in recipes
    ]
    return {
        "recipes_items": items,
        "recipes_message": message,
        "recipes_error": error,
        "recipes_saved": saved,
        "saved_recipe": saved or loaded,
    }


async def _panel(request: Request, **kwargs: Any) -> HTMLResponse:
    ctx = common_ctx()
    ctx.update(await panel_context(**kwargs))
    return templates.TemplateResponse(request, "partials/recipes_panel.html", ctx)


@router.post("", response_class=HTMLResponse)
async def save_recipe(request: Request) -> HTMLResponse:
    form = await request.form()
    data = {k: str(v) for k, v in form.items()}
    name = data.get("save_name", "").replace("\x00", "").strip()[:MAX_NAME]
    if not name:
        return await _panel(request, error="Dai un nome alla ricetta per salvarla.")
    message = data.get("save_message", "").replace("\x00", "").strip()[:MAX_MESSAGE]
    payload = payload_from_form(data)
    if not payload["phases"]:
        return await _panel(request, error="Aggiungi almeno una fase prima di salvare.")
    preset = PRESETS_BY_KEY.get(payload["preset_key"])

    async with SessionLocal() as session:
        recipe = await session.scalar(
            select(Recipe).where(Recipe.name == name).options(selectinload(Recipe.versions))
        )
        if recipe is None:
            recipe = Recipe(name=name, style=preset.style.value if preset else RecipeStyle.NAPOLETANA.value)
            session.add(recipe)
            version_no = 1
        else:
            version_no = max(v.version for v in recipe.versions) + 1 if recipe.versions else 1
        recipe.versions.append(RecipeVersion(version=version_no, message=message, payload=payload))
        await session.commit()
        saved = {"id": recipe.id, "name": recipe.name, "version": version_no}
    verb = "salvata" if version_no == 1 else f"aggiornata (nuova versione v{version_no})"
    return await _panel(request, message=f"Ricetta «{name}» {verb}.", saved=saved)


@router.post("/{recipe_id:int}/elimina", response_class=HTMLResponse)
async def delete_recipe(request: Request, recipe_id: RowId) -> HTMLResponse:
    async with SessionLocal() as session:
        recipe = await session.get(Recipe, recipe_id, options=[selectinload(Recipe.versions)])
        if recipe is not None:
            await session.delete(recipe)
            await session.commit()
    return await _panel(request, message="Ricetta eliminata. Le prove del diario restano.")
