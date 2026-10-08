"""Test della modalità guidata: strategie di lievitazione, fasi generate e passaggio a Esperto."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from doughlab.models import RecipeVersion
from doughlab.planning import compute_plan_and_ingredients
from doughlab.services.scheduler import PhaseKind
from doughlab.services.strategies import STRATEGIES, build_phases, strategy_for
from doughlab.services.thermal import Container, Environment

from .test_diary import run_with_db
from .test_main import _form
from .test_recipes import _save_data


def _guided(**extra: str) -> dict[str, str]:
    data = {k: v for k, v in _form(62).items() if not k.startswith("phase_")}
    data.update(mode="guided", strategy="fridge_24", room_c="22", fridge_c="4")
    data.update(extra)
    return data


def test_every_strategy_builds_phases_that_add_up_to_its_total() -> None:
    for strategy in STRATEGIES:
        phases = build_phases(strategy.key, 22, 4)
        maturation = sum(p.hours for p in phases if p.kind != PhaseKind.MIX)

        assert maturation == pytest.approx(strategy.total_h), strategy.key
        assert phases[0].kind == PhaseKind.MIX
        assert phases[-1].kind == PhaseKind.PROOF


def test_fridge_phases_use_the_fridge_temperature_and_the_rest_the_kitchen_one() -> None:
    phases = build_phases("fridge_24", room_c=30, fridge_c=6)

    cold = [p for p in phases if p.environment == Environment.FRIDGE_HOME]
    warm = [p for p in phases if p.environment == Environment.AMBIENT]
    assert [p.kind for p in cold] == [PhaseKind.MATURATION] and cold[0].ambient_c == 6
    assert warm and all(p.ambient_c == 30 for p in warm)


def test_direct_strategy_has_no_fridge_and_solo_frigo_matures_the_balls() -> None:
    assert not any(p.environment == Environment.FRIDGE_HOME for p in build_phases("direct_8", 22, 4))

    phases = build_phases("fridge_only_24", 22, 4)
    kinds = [p.kind for p in phases]
    assert kinds.index(PhaseKind.SHAPE) < kinds.index(PhaseKind.MATURATION)
    assert phases[kinds.index(PhaseKind.MATURATION)].container == Container.BALLS_BOX


def test_preferment_and_open_phases_are_added_around_the_strategy() -> None:
    phases = build_phases("fridge_24", 22, 4, preferment_hours=18, preferment_label="Biga", open_hours=1)

    assert phases[0].kind == PhaseKind.PREFERMENT and phases[0].label == "Biga"
    assert phases[-1].kind == PhaseKind.OPEN


def test_unknown_strategy_falls_back_to_the_default() -> None:
    assert strategy_for("nonsense").key == "fridge_24"


def test_guided_plan_ignores_the_phase_fields_and_expert_plan_uses_them() -> None:
    guided = compute_plan_and_ingredients({**_form(62), "mode": "guided", "strategy": "long_72"})
    expert = compute_plan_and_ingredients({**_form(62), "mode": "expert", "strategy": "long_72"})
    legacy = compute_plan_and_ingredients(_form(62))

    assert guided["plan"].total_hours > 70
    assert expert["plan"].total_hours < 30
    assert expert["plan"].total_hours == pytest.approx(legacy["plan"].total_hours)


def test_hot_kitchen_lowers_the_suggested_yeast_in_guided_mode() -> None:
    cool = compute_plan_and_ingredients(_guided(room_c="20"))
    hot = compute_plan_and_ingredients(_guided(room_c="30"))

    assert hot["suggested_pct"] < cool["suggested_pct"]


def test_guided_temperatures_are_clamped_not_trusted() -> None:
    plan = compute_plan_and_ingredients(_guided(room_c="9999", fridge_c="-50"))["plan"]

    assert all(-5 <= p.phase.ambient_c <= 50 for p in plan.phases)


def test_guided_plan_with_a_preferment_starts_with_it() -> None:
    plan = compute_plan_and_ingredients(
        _guided(preferment_pct="30", preferment_hydration_pct="44")
    )["plan"]

    assert plan.phases[0].phase.kind == PhaseKind.PREFERMENT
    assert plan.phases[0].phase.label == "Biga"


def test_planner_page_offers_steps_modes_and_all_strategies(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        page = (await client.get("/")).text

        assert "plannerUI('split', 'guided', false)" in page
        assert 'name="mode" value="guided"' in page
        assert page.count('name="strategy"') == len(STRATEGIES)
        assert 'name="room_c"' in page and 'name="fridge_c"' in page
        assert 'id="planBar"' in page and 'id="flourAdvice"' in page
        assert page.index("Ricetta base") < page.index("Come lieviti") < page.index('id="result"')

    run_with_db(tmp_path, monkeypatch, check)


def test_phases_endpoint_returns_the_phases_of_the_chosen_strategy(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        response = await client.post("/fasi", data=_guided(strategy="direct_8", room_c="28"))

        assert response.status_code == 200
        assert response.text.count('class="phase-card"') == 4
        assert 'name="phase_ambient_1" value="28.0"' in response.text

    run_with_db(tmp_path, monkeypatch, check)


def test_plan_response_carries_the_advice_and_the_summary_bar(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        text = (await client.post("/plan", data=_guided())).text

        assert 'id="planBar" hx-swap-oob="innerHTML"' in text
        assert 'id="flourAdvice" hx-swap-oob="innerHTML"' in text

    run_with_db(tmp_path, monkeypatch, check)


def test_saved_recipe_keeps_its_mode_and_old_recipes_open_in_expert(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        guided = _save_data("Guidata", mode="guided", strategy="long_72", room_c="28", fridge_c="6")
        await client.post("/ricette", data=guided)
        page = (await client.get("/?recipe=1")).text
        assert "plannerUI('home', 'guided', true)" in page
        assert 'value="long_72" checked' in page and 'name="room_c" value="28"' in page

        await client.post("/ricette", data=_save_data("Vecchia"))
        async with sessions() as session:
            version = await session.scalar(select(RecipeVersion).where(RecipeVersion.recipe_id == 2))
            assert version is not None
            version.payload = {
                k: v for k, v in version.payload.items() if k not in {"mode", "strategy", "room_c", "fridge_c"}
            }
            await session.commit()
        assert "plannerUI('home', 'expert', true)" in (await client.get("/?recipe=2")).text

    run_with_db(tmp_path, monkeypatch, check)
