"""Test della temperatura dell'acqua e dell'infornata a ritroso."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from doughlab.planning import compute_plan_and_ingredients, hours_before_bake
from doughlab.services.backup import KNEADING_LABELS
from doughlab.services.scheduler import PhaseKind, PlanPhase
from doughlab.services.water import FRICTION_RISE_C, water_temperature

from .test_diary import run_with_db
from .test_recipes import _save_data
from .test_strategies import _guided


def test_water_follows_the_three_factor_formula_and_friction() -> None:
    assert water_temperature(24, 22, 20, "hand").temperature_c == pytest.approx(27.0)
    assert water_temperature(24, 22, 20, "planetary").temperature_c == pytest.approx(16.5)
    assert water_temperature(24, 22, 20, "mixer").temperature_c == pytest.approx(15.0)
    assert water_temperature(24, 22, 20, "unknown").temperature_c == pytest.approx(27.0)
    assert water_temperature(24, 22, 20, "hand").formula == "3 × 24 − (22 + 20 + 3)"


def test_a_preferment_adds_its_temperature_and_a_fourth_factor() -> None:
    advice = water_temperature(24, 22, 20, "hand", preferment_c=18)

    assert advice.temperature_c == pytest.approx(4 * 24 - (22 + 20 + 18 + 4))
    assert advice.formula.startswith("4 × 24")


def test_hot_summer_asks_for_cold_water_and_ice_when_it_is_not_enough() -> None:
    summer = water_temperature(24, 30, 28, "hand")
    brutal = water_temperature(24, 34, 32, "mixer")

    assert summer.temperature_c == pytest.approx(11.0) and summer.level == "ok"
    assert summer.dough_c == pytest.approx(24)
    assert brutal.level == "cold" and "ghiaccio" in brutal.message
    assert brutal.temperature_c == 0 and brutal.wanted_c == pytest.approx(-9)
    assert brutal.dough_c == pytest.approx(27)


def test_water_is_capped_at_35_degrees_and_the_resulting_dough_temperature_is_reported() -> None:
    winter = water_temperature(24, 12, 15, "hand")

    assert winter.wanted_c == pytest.approx(42.0)
    assert winter.temperature_c == 35 and winter.level == "hot"
    assert winter.dough_c == pytest.approx(21.7)
    assert "42,0" in winter.message and "35" in winter.message and "21,7" in winter.message
    assert water_temperature(24, 16, 14, "hand").temperature_c == 35


def test_plan_uses_the_dough_temperature_that_the_capped_water_gives() -> None:
    cold = compute_plan_and_ingredients(_guided(room_c="12", flour_c="15", kneading="hand"))

    assert cold["water"].temperature_c == 35
    assert cold["plan_snapshot"]["initial_dough_c"] == cold["water"].dough_c < 24
    assert cold["plan_snapshot"]["water_c"] == 35


def test_planner_and_diary_use_the_same_kneading_keys() -> None:
    assert set(FRICTION_RISE_C) == set(KNEADING_LABELS)


def test_hours_before_bake_stops_at_a_bake_phase() -> None:
    def phase(kind: PhaseKind, hours: float) -> PlanPhase:
        return PlanPhase(kind=kind, label=kind.value, hours=hours, ambient_c=22)

    phases = [phase(PhaseKind.MIX, 0.5), phase(PhaseKind.PROOF, 4), phase(PhaseKind.BAKE, 0.25)]

    assert hours_before_bake(phases) == 4.5
    assert hours_before_bake(phases[:2]) == 4.5


def test_reverse_scheduling_starts_the_right_time_before_the_oven() -> None:
    bake = datetime.now().replace(second=0, microsecond=0) + timedelta(days=4)
    data = _guided(anchor="bake", bake_at=bake.strftime("%Y-%m-%dT%H:%M"), start_at="2020-01-01T08:00")

    result = compute_plan_and_ingredients(data)
    plan = result["plan"]

    assert result["anchor"] == "bake"
    assert result["plan_oven_at"] == bake
    assert result["plan_start_at"] == bake - timedelta(hours=plan.total_hours)
    assert plan.phases[0].start_at == result["plan_start_at"]
    assert plan.end_at == bake
    assert result["plan_snapshot"]["started_at"] == result["plan_start_at"].isoformat()
    assert not result["start_in_past"]


def test_start_mode_ignores_the_oven_time_and_bad_values_fall_back() -> None:
    start_mode = compute_plan_and_ingredients(_guided(bake_at="2031-01-01T20:00", start_at="2031-01-01T08:00"))
    broken = compute_plan_and_ingredients(_guided(anchor="bake", bake_at="non una data", start_at="2031-01-01T08:00"))

    assert start_mode["anchor"] == "start" and start_mode["plan_start_at"] == datetime(2031, 1, 1, 8)
    assert broken["anchor"] == "start" and broken["plan_start_at"] == datetime(2031, 1, 1, 8)


def test_an_oven_time_too_close_is_flagged_as_start_in_the_past() -> None:
    soon = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")

    assert compute_plan_and_ingredients(_guided(anchor="bake", bake_at=soon))["start_in_past"]


def test_plan_exposes_water_and_a_hot_kitchen_cools_it() -> None:
    cool = compute_plan_and_ingredients(_guided(room_c="22", flour_c="20", kneading="hand"))
    hot = compute_plan_and_ingredients(_guided(room_c="30", flour_c="26", kneading="planetary"))

    assert cool["water"].temperature_c == pytest.approx(27.0)
    assert hot["water"].temperature_c < cool["water"].temperature_c
    assert hot["plan_snapshot"]["kneading"] == "planetary" and hot["plan_snapshot"]["water_c"] == hot["water"].temperature_c


def test_plan_response_and_page_carry_the_new_fields(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        text = (await client.post("/plan", data=_guided(anchor="bake", bake_at="2031-05-05T20:30"))).text
        assert 'id="startInfo" hx-swap-oob="innerHTML"' in text and "devi iniziare" in text
        assert 'id="waterInfo" class="water-info ok"' in text and "Temperatura dell'acqua" in text
        assert "a 27,0 °C" in text

        page = (await client.get("/")).text
        for field in ('name="anchor"', 'name="bake_at"', 'name="flour_c"', 'name="kneading"'):
            assert field in page
        assert page.count('<option value="') >= len(KNEADING_LABELS)
        assert "A mano (+1 °C)" in page and "Planetaria (+4,5 °C)" in page

    run_with_db(tmp_path, monkeypatch, check)


def test_saved_recipe_remembers_flour_temperature_and_kneading(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await client.post("/ricette", data=_save_data("Estate", flour_c="26", kneading="mixer"))
        page = (await client.get("/?recipe=1")).text

        assert 'name="flour_c" value="26"' in page
        assert '<option value="mixer" selected>' in page

    run_with_db(tmp_path, monkeypatch, check)


def test_diary_from_plan_prefills_kneading_and_water_temperature(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        response = await client.post("/diario/da-piano", data=_guided(kneading="planetary", flour_c="20"))

        assert '<option value="planetary" selected>' in response.text
        assert "Acqua " in response.text and " °C" in response.text

    run_with_db(tmp_path, monkeypatch, check)
