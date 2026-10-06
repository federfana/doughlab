"""Test del collegamento tra form, suggerimento lievito e grammature."""
from __future__ import annotations

import asyncio
import json
import math
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from doughlab.db import Base
from doughlab.main import (
    _bake_history_item,
    _common_ctx,
    _compute_plan_and_ingredients,
    _default_recipe_ctx,
    _make_bake_record,
    _preset_ctx,
    app,
    templates,
)
from doughlab.models import Bake
from doughlab.services.fermentation import YeastKind


def _form(hydration_pct: int) -> dict[str, str]:
    return {
        "start_at": "2026-10-03T11:00",
        "initial_dough_c": "24",
        "yeast_kind": "fresh",
        "panetto_g": "250",
        "n_panetti": "4",
        "hydration_pct": str(hydration_pct),
        "salt_pct": "2.8",
        "phase_kind_0": "mix",
        "phase_label_0": "Impasto",
        "phase_hours_0": "0.5",
        "phase_ambient_0": "22",
        "phase_container_0": "mass_bowl",
        "phase_env_0": "ambient",
        "phase_kind_1": "bulk",
        "phase_label_1": "Puntata",
        "phase_hours_1": "2",
        "phase_ambient_1": "22",
        "phase_container_1": "mass_bowl",
        "phase_env_1": "ambient",
        "phase_kind_2": "shape",
        "phase_label_2": "Staglio",
        "phase_hours_2": "0.5",
        "phase_ambient_2": "22",
        "phase_container_2": "balls_box",
        "phase_env_2": "ambient",
        "phase_kind_3": "proof",
        "phase_label_3": "Appretto",
        "phase_hours_3": "6",
        "phase_ambient_3": "22",
        "phase_container_3": "balls_box",
        "phase_env_3": "ambient",
    }


def test_suggested_yeast_is_used_for_plan_and_weights() -> None:
    result = _compute_plan_and_ingredients(_form(62))

    assert result["ingredients"].yeast_pct == result["suggested_pct"]
    assert result["weights"].yeast_g == result["weights"].flour_g * result["suggested_pct"]
    assert 0.001 < result["suggested_pct"] < 0.01
    assert result["plan"].fermentation.final_pct == pytest.approx(100.0)


def test_hydration_change_recalculates_all_ingredient_weights() -> None:
    lower = _compute_plan_and_ingredients(_form(60))
    higher = _compute_plan_and_ingredients(_form(70))

    assert higher["weights"].flour_g < lower["weights"].flour_g
    assert higher["weights"].water_g > lower["weights"].water_g
    assert higher["weights"].yeast_g < lower["weights"].yeast_g
    assert lower["weights"].total_g == pytest.approx(1000.0)
    assert higher["weights"].total_g == pytest.approx(1000.0)


def test_schedule_duration_changes_yeast_suggestion_not_formula_percentages() -> None:
    short_form = _form(65)
    long_form = _form(65)
    long_form["phase_hours_1"] = "8"

    short = _compute_plan_and_ingredients(short_form)
    long = _compute_plan_and_ingredients(long_form)

    assert short["suggested_pct"] != pytest.approx(long["suggested_pct"])
    assert short["ingredients"].hydration_pct == long["ingredients"].hydration_pct
    assert short["ingredients"].salt_pct == long["ingredients"].salt_pct


@pytest.mark.parametrize("phase_kind", ["autolyse", "bake"])
def test_non_fermenting_phase_duration_does_not_change_yeast_suggestion(
    phase_kind: str,
) -> None:
    short_form = _form(65)
    long_form = _form(65)
    short_form["initial_dough_c"] = "22"
    long_form["initial_dough_c"] = "22"
    short_form["phase_kind_2"] = phase_kind
    long_form["phase_kind_2"] = phase_kind
    long_form["phase_hours_2"] = "3"

    short = _compute_plan_and_ingredients(short_form)
    long = _compute_plan_and_ingredients(long_form)

    assert short["suggested_pct"] == pytest.approx(long["suggested_pct"])


def _render_plan_summary(data: dict[str, str]) -> str:
    context = _common_ctx()
    context.update(_compute_plan_and_ingredients(data))
    return templates.get_template("partials/plan_result.html").render(**context)


def test_summary_combines_ready_and_end_when_they_match() -> None:
    rendered = _render_plan_summary(_form(65))

    assert "Pronto e fine ultima fase" in rendered
    assert "<dt>Fine ultima fase</dt>" not in rendered
    assert 'id="bakeHistory"' in rendered
    assert 'hx-swap-oob="outerHTML"' in rendered


def test_summary_separates_ready_from_later_bake_phase() -> None:
    data = _form(65)
    data.update(
        phase_kind_4="bake",
        phase_label_4="Cottura",
        phase_hours_4="0.25",
        phase_ambient_4="220",
        phase_container_4="mass_bowl",
        phase_env_4="ambient",
    )
    rendered = _render_plan_summary(data)

    assert "Pronto per la cottura" in rendered
    assert "<dt>Fine ultima fase</dt>" in rendered


def test_chart_x_axis_uses_elapsed_hours_not_sample_indexes() -> None:
    rendered = _render_plan_summary(_form(65))

    assert "type: 'linear'" in rendered
    assert "d.t.map((x, i) => ({ x, y: d.dough[i] }))" in rendered
    assert "max: d.t[d.t.length - 1]" in rendered


def test_chart_has_fixed_responsive_height_and_follows_theme() -> None:
    rendered = _render_plan_summary(_form(65))

    assert 'class="chart-wrap"' in rendered
    assert "maintainAspectRatio: false" in rendered
    assert "window.__redrawChart" in rendered
    assert "css('--ink-2'" in rendered


def test_planner_shows_primary_inputs_and_hides_manual_yeast_dose() -> None:
    context = _common_ctx()
    context["recipe"] = _default_recipe_ctx()
    rendered = templates.get_template("planner.html").render(**context)

    for name in ("n_panetti", "panetto_g", "hydration_pct", "salt_pct"):
        assert f'name="{name}"' in rendered
    assert 'name="yeast_pct"' not in rendered
    assert 'name="hydration_pct"' in rendered
    assert 'name="salt_pct"' in rendered
    assert 'step="any"' in rendered
    assert 'aria-label="Aumenta idratazione di 1 punto"' in rendered
    assert 'aria-label="Riduci sale di 1 punto"' in rendered
    assert rendered.index('id="result"') < rendered.index('name="start_at"')
    assert rendered.index('id="result"') < rendered.index('Ricetta base')
    assert 'id="detailsResult"' in rendered
    assert rendered.count('<input type="radio" name="yeast_kind"') == 3
    assert '<select name="yeast_kind"' not in rendered
    assert rendered.index('name="yeast_kind"') < rendered.index('<details class="panel">')
    assert rendered.count('role="tab"') == 2
    assert rendered.index('id="panel-planner"') < rendered.index('id="panel-registry"')
    assert 'id="panel-registry"' in rendered
    assert 'id="bakeHistory"' in rendered


def test_selected_yeast_type_survives_recipe_change() -> None:
    recipe = _preset_ctx("teglia", YeastKind.SOURDOUGH)

    assert recipe is not None
    assert recipe["yeast_kind"] == YeastKind.SOURDOUGH.value


@pytest.mark.parametrize("oven_profile", ["split", "home"])
def test_oven_profile_survives_recipe_change(oven_profile: str) -> None:
    recipe = _preset_ctx("teglia", YeastKind.SOURDOUGH, oven_profile)

    assert recipe is not None
    assert recipe["oven_profile"] == oven_profile
    assert recipe["yeast_kind"] == YeastKind.SOURDOUGH.value


def test_legacy_nettuno_oven_profile_maps_to_split_heaters() -> None:
    recipe = _preset_ctx("teglia", oven_profile="nettuno")

    assert recipe is not None
    assert recipe["oven_profile"] == "split"


def test_teglia_preset_shows_split_oven_cielo_and_platea_advice() -> None:
    context = _common_ctx()
    context["recipe"] = _preset_ctx("teglia", oven_profile="split")
    rendered = templates.get_template("planner.html").render(**context)

    assert 'name="bake_plate_c"' not in rendered
    assert 'name="bake_ceiling_c"' not in rendered
    assert "310 °C" in rendered
    assert "200 °C" in rendered
    assert "platea 300-320 °C, cielo circa 200 °C" in rendered
    assert "MacteOvens Nettuno" not in rendered


def test_bake_observation_saves_snapshot_and_prediction_delta() -> None:
    snapshot = {
        "recipe_name": "Teglia romana 24h",
        "started_at": "2026-10-03T10:00",
        "predicted_ready_at": "2026-10-04T10:00",
        "yeast_kind": "fresh",
        "yeast_pct": 0.001,
        "phases": [{"kind": "proof", "hours": 4}],
    }
    record, delta, saved_snapshot = _make_bake_record(
        {
            "snapshot_json": json.dumps(snapshot),
            "actual_ready_at": "2026-10-04T11:30",
            "observed_dough_c": "22",
            "rating": "4",
            "notes": "Impasto estensibile",
            "actual_oven_profile": "split",
            "actual_preheat_minutes": "45",
            "actual_plate_c": "405",
            "actual_ceiling_c": "475",
            "actual_bake_minutes": "1.5",
            "actual_bake_position": "Ripiano alto",
        }
    )
    view = _bake_history_item(record)

    assert saved_snapshot == snapshot
    assert delta == pytest.approx(1.5)
    assert record.log[1]["observed_dough_c"] == 22
    assert record.log[1]["baking"] == {
        "oven_profile": "split",
        "preheat_minutes": 45.0,
        "plate_c": 405.0,
        "ceiling_c": 475.0,
        "bake_minutes": 1.5,
        "bake_position": "Ripiano alto",
    }
    assert view["baking"]["plate_c"] == 405.0
    assert view["delta_hours"] == pytest.approx(1.5)
    assert record.rating == 4


def test_cooking_advice_is_not_overridden_by_planner_form() -> None:
    data = _form(65)
    data.update(
        preset_key="teglia",
        oven_profile="home",
        preheat_c="180",
        preheat_minutes="45",
        bake_c="180",
        home_bake_minutes="18",
        home_bake_position="Ripiano basso",
    )
    result = _compute_plan_and_ingredients(data)

    assert result["baking"]["bake_c"] == 250
    assert result["baking"]["position"] == "Ripiano basso per la base, poi medio per dorare"
    assert result["bake_snapshot"]["baking"] == result["baking"]
    assert result["plan"].fermentation.final_pct == pytest.approx(100.0)


def test_split_oven_profile_keeps_preset_platea_and_ceiling_advice() -> None:
    data = _form(65)
    data.update(
        oven_profile="split",
        preheat_minutes="35",
        bake_plate_c="410",
        bake_ceiling_c="485",
        split_bake_minutes="1.5",
    )
    result = _compute_plan_and_ingredients(data)

    assert result["baking"]["plate_c"] == 420
    assert result["baking"]["ceiling_c"] == 485.0
    assert result["baking"]["bake_minutes"] == 1.25
    assert result["baking"]["position"] == "Pietra"
    assert result["bake_snapshot"]["baking"]["plate_c"] == 420
    assert result["baking"]["mode"] == "Forno elettrico con cielo e platea indipendenti"


def test_bake_route_persists_observation_in_sqlite(tmp_path, monkeypatch) -> None:
    async def run() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bakes.sqlite3'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr("doughlab.main.SessionLocal", sessions)

        snapshot = {
            "recipe_name": "Teglia romana 24h",
            "started_at": "2026-10-03T10:00",
            "predicted_ready_at": "2026-10-04T10:00",
            "yeast_kind": "fresh",
            "yeast_pct": 0.001,
            "baking": {
                "oven_profile": "split",
                "preheat_minutes": 30,
                "plate_c": 310,
                "ceiling_c": 200,
                "bake_minutes": 10,
                "position": "Ripiano basso",
            },
            "phases": [{"kind": "proof", "hours": 4}],
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/bakes",
                data={
                    "snapshot_json": json.dumps(snapshot),
                    "actual_ready_at": "2026-10-04T10:30",
                    "observed_dough_c": "22",
                    "rating": "5",
                    "notes": "Buona estensibilità",
                    "actual_oven_profile": "split",
                    "actual_preheat_minutes": "35",
                    "actual_plate_c": "320",
                    "actual_ceiling_c": "210",
                    "actual_bake_minutes": "12",
                    "actual_bake_position": "Ripiano alto",
                },
            )

        assert response.status_code == 200
        assert "0.5 h dopo" in response.text
        async with sessions() as session:
            record = await session.scalar(select(Bake))
        assert record is not None
        assert record.rating == 5
        assert record.notes == "Buona estensibilità"
        assert record.log[0]["snapshot"]["recipe_name"] == "Teglia romana 24h"
        assert record.log[1]["actual_ready_at"] == "2026-10-04T10:30:00"
        assert record.log[1]["baking"]["plate_c"] == 320.0
        assert record.log[1]["baking"]["bake_position"] == "Ripiano alto"
        assert "Platea 320 °C" in response.text
        assert "Cottura 12.0 min" in response.text
        assert "Ripiano alto" in response.text
        await engine.dispose()

    asyncio.run(run())


def test_phase_cards_explain_temperature_and_preset_effects() -> None:
    context = _common_ctx()
    context["recipe"] = _preset_ctx("teglia")
    rendered = templates.get_template("planner.html").render(**context)

    assert "Idratazione 75%, olio 3% e maturazione in frigorifero." in rendered
    assert "circa 13% di proteine" in rendered
    assert "TA = temperatura ambiente; TC = temperatura controllata." in rendered
    assert 'name="phase_hours_0"' in rendered
    assert 'name="phase_env_0"' in rendered
    assert 'name="phase_ambient_0"' in rendered
    assert rendered.index('name="n_panetti"') < rendered.index('id="result"')


@pytest.mark.parametrize(
    "overrides",
    [
        {"phase_hours_0": "inf"},
        {"phase_hours_0": "nan"},
        {"phase_hours_0": "1e12"},
        {"phase_hours_0": "-5"},
        {"initial_dough_c": "abc"},
        {"initial_dough_c": "nan"},
        {"start_at": "garbage"},
        {"yeast_kind": "x"},
        {"target_work": "0"},
    ],
)
def test_hostile_form_values_never_hang_or_produce_non_finite_plans(overrides: dict[str, str]) -> None:
    data = _form(65)
    data.update(overrides)
    result = _compute_plan_and_ingredients(data)

    assert result["plan"].total_hours <= 720 * 4
    assert math.isfinite(result["suggested_pct"])
    assert all(math.isfinite(x) for x in result["plan"].fermentation.maturity_pct)


def test_phase_count_is_capped() -> None:
    data = _form(65)
    for i in range(4, 60):
        data.update({
            f"phase_kind_{i}": "bulk", f"phase_label_{i}": "x", f"phase_hours_{i}": "1",
            f"phase_ambient_{i}": "22", f"phase_container_{i}": "mass_bowl",
            f"phase_env_{i}": "ambient",
        })

    assert len(_compute_plan_and_ingredients(data)["plan"].phases) == 30


def test_ics_export_uses_local_time_not_utc() -> None:
    async def run() -> str:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return (await client.post("/plan.ics", data=_form(65))).text

    expected = datetime.fromisoformat("2026-10-03T11:00").astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")

    assert f"DTSTART:{expected}" in asyncio.run(run())


def test_bake_form_never_embeds_snapshot_text_in_javascript(tmp_path, monkeypatch) -> None:
    async def run() -> tuple[str, str]:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bakes.sqlite3'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        monkeypatch.setattr(
            "doughlab.main.SessionLocal", async_sessionmaker(engine, expire_on_commit=False)
        )
        hostile = {
            "started_at": "2026-10-03T10:00",
            "baking": {"oven_profile": "x');alert(1);//"},
            "baking_options": {"split": {"position": "<script>alert(1)</script>"}},
        }
        texts = []
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for snapshot in (hostile, [1, 2]):
                response = await client.post(
                    "/bakes",
                    data={"snapshot_json": json.dumps(snapshot), "actual_ready_at": "garbage"},
                )
                assert response.status_code == 200
                texts.append(response.text)
        await engine.dispose()
        return texts[0], texts[1]

    hostile_text, list_text = asyncio.run(run())

    assert "<script>alert(1)" not in hostile_text
    assert "x');alert(1)" not in hostile_text
    assert "Calcola un piano" in list_text
