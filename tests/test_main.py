"""Test del collegamento tra form, suggerimento lievito e grammature."""
from __future__ import annotations

import asyncio
import math
import re
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from doughlab.main import app
from doughlab.planning import (
    compute_plan_and_ingredients,
    default_recipe_ctx,
    preset_ctx,
)
from doughlab.services.fermentation import YeastKind
from doughlab.web import common_ctx as _common_ctx
from doughlab.web import templates


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
    result = compute_plan_and_ingredients(_form(62))

    assert result["ingredients"].yeast_pct == result["suggested_pct"]
    assert result["weights"].yeast_g == result["weights"].flour_g * result["suggested_pct"]
    assert 0.001 < result["suggested_pct"] < 0.01
    assert result["plan"].fermentation.final_pct == pytest.approx(100.0)


def test_hydration_change_recalculates_all_ingredient_weights() -> None:
    lower = compute_plan_and_ingredients(_form(60))
    higher = compute_plan_and_ingredients(_form(70))

    assert higher["weights"].flour_g < lower["weights"].flour_g
    assert higher["weights"].water_g > lower["weights"].water_g
    assert higher["weights"].yeast_g < lower["weights"].yeast_g
    assert lower["weights"].total_g == pytest.approx(1000.0)
    assert higher["weights"].total_g == pytest.approx(1000.0)


def test_schedule_duration_changes_yeast_suggestion_not_formula_percentages() -> None:
    short_form = _form(65)
    long_form = _form(65)
    long_form["phase_hours_1"] = "8"

    short = compute_plan_and_ingredients(short_form)
    long = compute_plan_and_ingredients(long_form)

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

    short = compute_plan_and_ingredients(short_form)
    long = compute_plan_and_ingredients(long_form)

    assert short["suggested_pct"] == pytest.approx(long["suggested_pct"])


def _render_plan_summary(data: dict[str, str]) -> str:
    context = _common_ctx()
    context.update(compute_plan_and_ingredients(data))
    return templates.get_template("partials/plan_result.html").render(**context)


def test_summary_combines_ready_and_end_when_they_match() -> None:
    rendered = _render_plan_summary(_form(65))

    assert "Pronto e fine ultima fase" in rendered
    assert "<dt>Fine ultima fase</dt>" not in rendered
    assert 'hx-post="/diario/da-piano"' in rendered
    assert 'id="bakeHistory"' not in rendered


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
    context["recipe"] = default_recipe_ctx()
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
    assert rendered.count('role="tab"') == 4
    assert rendered.index('id="panel-planner"') < rendered.index('id="panel-live"') < rendered.index('id="panel-diary"') < rendered.index('id="panel-flours"')
    assert 'id="panel-diary"' in rendered
    assert 'id="diaryPanel"' in rendered
    assert "Registro prove" not in rendered


def test_selected_yeast_type_survives_recipe_change() -> None:
    recipe = preset_ctx("teglia", YeastKind.SOURDOUGH)

    assert recipe is not None
    assert recipe["yeast_kind"] == YeastKind.SOURDOUGH.value


@pytest.mark.parametrize("oven_profile", ["split", "home"])
def test_oven_profile_survives_recipe_change(oven_profile: str) -> None:
    recipe = preset_ctx("teglia", YeastKind.SOURDOUGH, oven_profile)

    assert recipe is not None
    assert recipe["oven_profile"] == oven_profile
    assert recipe["yeast_kind"] == YeastKind.SOURDOUGH.value


def test_legacy_nettuno_oven_profile_maps_to_split_heaters() -> None:
    recipe = preset_ctx("teglia", oven_profile="nettuno")

    assert recipe is not None
    assert recipe["oven_profile"] == "split"


def test_teglia_preset_shows_split_oven_cielo_and_platea_advice() -> None:
    context = _common_ctx()
    context["recipe"] = preset_ctx("teglia", oven_profile="split")
    rendered = templates.get_template("planner.html").render(**context)

    assert 'name="bake_plate_c"' not in rendered
    assert 'name="bake_ceiling_c"' not in rendered
    assert "310 °C" in rendered
    assert "200 °C" in rendered
    assert "platea 300-320 °C, cielo circa 200 °C" in rendered
    assert "MacteOvens Nettuno" not in rendered


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
    result = compute_plan_and_ingredients(data)

    assert result["baking"]["bake_c"] == 250
    assert result["baking"]["position"] == "Ripiano basso per la base, poi medio per dorare"
    assert result["plan_snapshot"]["baking"] == result["baking"]
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
    result = compute_plan_and_ingredients(data)

    assert result["baking"]["plate_c"] == 420
    assert result["baking"]["ceiling_c"] == 485.0
    assert result["baking"]["bake_minutes"] == 1.25
    assert result["baking"]["position"] == "Pietra"
    assert result["plan_snapshot"]["baking"]["plate_c"] == 420
    assert result["baking"]["mode"] == "Forno elettrico con cielo e platea indipendenti"


def test_phase_cards_explain_temperature_and_preset_effects() -> None:
    context = _common_ctx()
    context["recipe"] = preset_ctx("teglia")
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
    result = compute_plan_and_ingredients(data)

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

    assert len(compute_plan_and_ingredients(data)["plan"].phases) == 30


def test_ics_export_uses_local_time_not_utc() -> None:
    async def run() -> str:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return (await client.post("/plan.ics", data=_form(65))).text

    expected = datetime.fromisoformat("2026-10-03T11:00").astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")

    assert f"DTSTART:{expected}" in asyncio.run(run())


def test_planner_numeric_inputs_accept_any_value_so_the_form_stays_valid() -> None:
    context = _common_ctx()
    context["recipe"] = default_recipe_ctx()
    rendered = templates.get_template("planner.html").render(**context)

    assert re.findall(r'<input type="number"[^>]*step="(?!any)[^"]*"', rendered) == []


def test_panetto_weight_is_not_rounded_to_multiples_of_ten() -> None:
    data = _form(65)
    data["panetto_g"] = "265"

    assert compute_plan_and_ingredients(data)["weights"].total_g == pytest.approx(1060.0)


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [(0, "0 min"), (0.5, "30 s"), (1.25, "1 min 15 s"), (8, "8 min"), (45, "45 min"),
     (60, "1 h"), (90, "1 h 30 min"), (24 * 60, "24 h")],
)
def test_durations_are_shown_in_hours_and_minutes_never_decimals(minutes: float, expected: str) -> None:
    from doughlab.services.fields import format_hours, format_minutes

    assert format_minutes(minutes) == expected
    assert format_hours(minutes / 60) == expected


def test_phase_duration_is_typed_as_hours_and_minutes_but_posted_as_decimal_hours() -> None:
    context = _common_ctx()
    recipe = default_recipe_ctx()
    recipe["phases"][1]["hours"] = 1.75
    context["recipe"] = recipe
    rendered = templates.get_template("planner.html").render(**context)

    assert 'class="dur-h" value="1"' in rendered
    assert 'class="dur-m" value="45"' in rendered
    assert 'name="phase_hours_1" value="1.75"' in rendered
    assert "Durata (ore)" not in rendered
    assert "1.25 min" not in rendered


def test_form_offers_only_casa_frigo_cella_and_ciotola_cassetta_with_icons() -> None:
    context = _common_ctx()
    context["recipe"] = default_recipe_ctx()
    rendered = templates.get_template("planner.html").render(**context)

    for option in ("🏠 TA · Casa", "❄️ TC · Frigo", "🌡️ TC · Cella", "🥣 Massa in ciotola", "📦 Panetti in cassetta"):
        assert option in rendered
    for retired in ("mass_box", "balls_single", "fridge_box", "Cassetta chiusa", "Panetto singolo"):
        assert f'value="{retired}"' not in rendered


def test_presets_only_use_offered_containers_and_environments() -> None:
    from doughlab.services.presets import PRESETS
    from doughlab.services.thermal import UI_CONTAINERS, UI_ENVIRONMENTS

    for preset in PRESETS:
        for phase in preset.phases:
            assert phase.container in UI_CONTAINERS
            assert phase.environment in UI_ENVIRONMENTS


def test_retired_container_and_environment_values_map_to_the_closest_offered_one() -> None:
    data = _form(65)
    data.update(
        phase_container_1="mass_box", phase_env_1="fridge_box",
        phase_container_2="balls_single", phase_env_2="chamber",
    )
    phases = compute_plan_and_ingredients(data)["plan_snapshot"]["phases"]

    assert phases[1]["environment"] == "fridge_home"
    assert phases[2]["environment"] == "chamber"


def test_teglia_preset_suggests_tray_formula_and_other_presets_do_not() -> None:
    context = _common_ctx()
    context["recipe"] = preset_ctx("teglia")
    teglia = templates.get_template("planner.html").render(**context)
    context["recipe"] = preset_ctx("napoletana")
    napoletana = templates.get_template("planner.html").render(**context)

    assert "lato × lato ÷ 2" in teglia
    assert 'class="tray-calc"' in teglia
    assert "tray-calc\"" not in napoletana


def test_stesura_phases_use_the_dough_ball_profile_not_the_bowl() -> None:
    from doughlab.services.presets import PRESETS_BY_KEY
    from doughlab.services.scheduler import PhaseKind
    from doughlab.services.thermal import Container

    for key in ("teglia", "pinsa"):
        stesure = [p for p in PRESETS_BY_KEY[key].phases if p.kind == PhaseKind.OPEN]
        assert stesure
        assert all(p.container == Container.BALLS_BOX for p in stesure)


def test_default_plan_starts_now_not_tomorrow() -> None:
    start = datetime.fromisoformat(default_recipe_ctx()["start_at"])

    assert abs((datetime.now() - start).total_seconds()) < 120
