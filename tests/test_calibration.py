"""Taratura del lievito sulle prove di una ricetta."""
from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlalchemy import select

from doughlab.models import RecipeVersion
from doughlab.services.calibration import Trial, calibrate, trial_hours

from .test_diary import run_with_db
from .test_recipes import _save_data


def test_trial_hours_needs_the_plan_and_the_real_times() -> None:
    plan = {"started_at": "2026-10-03T10:00", "predicted_ready_at": "2026-10-03T20:00"}

    assert trial_hours(plan, datetime(2026, 10, 3, 10), datetime(2026, 10, 3, 22)) == (10.0, 12.0)
    assert trial_hours(plan, None, datetime(2026, 10, 3, 22)) is None
    assert trial_hours({"predicted_ready_at": "2026-10-03T20:00"}, datetime(2026, 10, 3, 10), datetime(2026, 10, 3, 22)) is None
    assert trial_hours(plan, datetime(2026, 10, 3, 22), datetime(2026, 10, 3, 10)) is None


def test_one_trial_shows_the_gap_but_does_not_suggest_a_change() -> None:
    result = calibrate([Trial(10, 12, 1.0)], 1.0)

    assert result is not None and result.trials == 1
    assert result.mean_delta_h == pytest.approx(2) and result.mean_ratio == pytest.approx(1.2)
    assert result.suggested_target is None


def test_slower_than_predicted_raises_the_target_and_faster_lowers_it() -> None:
    slower = calibrate([Trial(10, 12, 1.0), Trial(10, 12, 1.0)], 1.0)
    faster = calibrate([Trial(10, 8, 1.0), Trial(10, 8, 1.0)], 1.0)

    assert slower is not None and slower.suggested_target == pytest.approx(1.2)
    assert faster is not None and faster.suggested_target == pytest.approx(0.8)


def test_trials_made_with_an_older_target_are_rescaled_to_the_current_one() -> None:
    # Con target 1.0 il reale era 1.2x; col target 1.2 la stima è già quella giusta.
    result = calibrate([Trial(10, 12, 1.0), Trial(10, 10, 1.2)], 1.2)

    assert result is not None and result.suggested_target is None


def test_small_gaps_outliers_and_big_jumps_are_handled() -> None:
    near = calibrate([Trial(10, 10.2, 1.0), Trial(10, 10.1, 1.0)], 1.0)
    typo = calibrate([Trial(10, 100, 1.0), Trial(10, 12, 1.0)], 1.0)
    huge = calibrate([Trial(10, 30, 1.0), Trial(10, 30, 1.0)], 1.0)

    assert near is not None and near.suggested_target is None
    assert typo is not None and typo.trials == 1
    assert huge is not None and huge.suggested_target == pytest.approx(1.5)
    assert calibrate([Trial(10, 100, 1.0)], 1.0) is None


def test_recipe_panel_proposes_the_calibration_and_applying_it_adds_a_version(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await client.post("/ricette", data=_save_data("Mia teglia"))
        plan = {
            "recipe_id": 1, "recipe_version": 1,
            "started_at": "2026-10-03T10:00", "predicted_ready_at": "2026-10-03T20:00",
        }
        for day in (3, 10):
            await client.post("/diario", data={
                "name": f"Prova {day}", "date": f"2026-10-{day:02d}", "plan_json": json.dumps(plan),
                "started_at": f"2026-10-{day:02d}T10:00", "ready_at": f"2026-10-{day:02d}T22:00",
            })

        page = (await client.get("/")).text
        assert "Stima e reale su 2 prove" in page and "aumentato del 20%" in page
        assert "/ricette/1/taratura" in page

        applied = await client.post("/ricette/1/taratura")
        assert "v2" in applied.text and "Riaprila" in applied.text
        async with sessions() as session:
            versions = (await session.scalars(select(RecipeVersion).order_by(RecipeVersion.version))).all()
            assert [v.version for v in versions] == [1, 2]
            assert versions[1].payload["target_work"] == pytest.approx(1.2)
            assert versions[1].payload["ingredients"] == versions[0].payload["ingredients"]

        again = await client.post("/ricette/1/taratura")
        assert "nessuna taratura" in again.text

    run_with_db(tmp_path, monkeypatch, check)
