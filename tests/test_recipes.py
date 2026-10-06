"""Test delle ricette salvate con versioning e del collegamento con il Diario."""
from __future__ import annotations

import json

from sqlalchemy import func, select

from doughlab.models import DiaryEntry, Recipe, RecipeVersion

from .test_diary import run_with_db
from .test_main import _form


def _save_data(name: str, hydration: int = 65, **extra: str) -> dict[str, str]:
    data = _form(hydration)
    data.update(save_name=name, preset_key="teglia", oven_profile="home", **extra)
    return data


def test_saving_same_name_creates_new_version_and_old_one_can_be_opened(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        first = await client.post("/ricette", data=_save_data("Mia teglia", 65))
        assert "salvata" in first.text
        second = await client.post("/ricette", data=_save_data("Mia teglia", 72, save_message="più acqua"))
        assert "nuova versione v2" in second.text
        assert 'id="recipeVersionField"' in second.text

        async with sessions() as session:
            assert await session.scalar(select(func.count(Recipe.id))) == 1
            versions = (await session.scalars(select(RecipeVersion).order_by(RecipeVersion.version))).all()
            assert [v.version for v in versions] == [1, 2]
            assert versions[1].message == "più acqua"

        latest = await client.get("/?recipe=1")
        assert 'name="hydration_pct" value="72.0"' in latest.text
        assert "aperta: Mia teglia v2" in latest.text
        old = await client.get("/?recipe=1&version=1")
        assert 'name="hydration_pct" value="65.0"' in old.text
        assert 'name="recipe_version" value="1"' in old.text

    run_with_db(tmp_path, monkeypatch, check)


def test_save_requires_name_and_ignores_missing_recipe(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        response = await client.post("/ricette", data=_save_data("  "))
        assert "Dai un nome alla ricetta" in response.text
        assert (await client.get("/?recipe=99")).status_code == 200
        assert (await client.get("/?recipe=abc&version=x")).status_code == 200

    run_with_db(tmp_path, monkeypatch, check)


def test_recipe_name_is_escaped_and_delete_removes_versions(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        response = await client.post("/ricette", data=_save_data("<script>alert(1)</script>"))
        assert "<script>alert(1)" not in response.text
        await client.post("/ricette/1/elimina")
        async with sessions() as session:
            assert await session.scalar(select(func.count(Recipe.id))) == 0
            assert await session.scalar(select(func.count(RecipeVersion.id))) == 0

    run_with_db(tmp_path, monkeypatch, check)


def test_diary_entry_keeps_recipe_link_and_can_be_filtered(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await client.post("/ricette", data=_save_data("Mia teglia"))
        plan = {"recipe_id": 1, "recipe_version": 1, "recipe_name": "Mia teglia"}
        await client.post("/diario", data={"name": "Con ricetta", "date": "2026-10-06", "plan_json": json.dumps(plan)})
        await client.post("/diario", data={"name": "Senza", "date": "2026-10-05", "notes": "croccante"})

        page = await client.get("/")
        assert "Ricetta Mia teglia v1" in page.text
        assert "1 prova" in page.text

        by_recipe = (await client.get("/diario?recipe=1")).text
        assert "Con ricetta" in by_recipe and "Senza" not in by_recipe
        assert "Ricetta: Mia teglia" in by_recipe

        by_text = (await client.get("/diario?q=CROCC")).text
        assert "Senza" in by_text and "Con ricetta" not in by_text
        assert "Nessuna prova corrisponde" in (await client.get("/diario?q=zzz")).text
        async with sessions() as session:
            assert await session.scalar(select(func.count(DiaryEntry.id))) == 2

    run_with_db(tmp_path, monkeypatch, check)


def test_plan_snapshot_carries_recipe_link() -> None:
    from doughlab.planning import compute_plan_and_ingredients

    data = _form(65)
    data.update(recipe_id="7", recipe_version="3")
    snapshot = compute_plan_and_ingredients(data)["plan_snapshot"]
    assert (snapshot["recipe_id"], snapshot["recipe_version"]) == (7, 3)
    assert compute_plan_and_ingredients(_form(65))["plan_snapshot"]["recipe_id"] is None


def test_saved_recipe_with_retired_container_opens_with_the_closest_offered_one(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        data = _save_data("Vecchia")
        data.update(phase_container_1="mass_box", phase_env_1="fridge_box")
        await client.post("/ricette", data=data)
        async with sessions() as session:
            version = await session.scalar(select(RecipeVersion))
            version.payload = {
                **version.payload,
                "phases": [
                    {**p, "container": "mass_box", "environment": "fridge_box"} for p in version.payload["phases"]
                ],
            }
            await session.commit()

        page = (await client.get("/?recipe=1")).text
        assert 'value="mass_bowl" selected' in page
        assert 'value="fridge_home" selected' in page
        assert 'value="mass_box"' not in page

    run_with_db(tmp_path, monkeypatch, check)
