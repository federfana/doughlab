"""Magazzino delle farine: dispensa, suggerimenti limitati a quanto hai in casa, consumo dalle prove."""
from __future__ import annotations

import json

from sqlalchemy import select

from doughlab.flours import seed_if_empty
from doughlab.models import DiaryEntry, Flour
from doughlab.services.pantry import format_grams, plan_consumption

from .test_diary import run_with_db
from .test_main import _form


async def _flour(sessions, name: str) -> Flour:
    async with sessions() as session:
        flour = await session.scalar(select(Flour).where(Flour.name == name))
        assert flour is not None
        return flour


async def _stock(sessions, name: str) -> float | None:
    return (await _flour(sessions, name)).stock_g


def _plan(**flours: float) -> dict:
    return {"ingredients": {"flour_g": 600}, "flours": [{"id": i, "pct": p} for i, p in flours.items()]}


def test_format_grams_uses_the_italian_thousands_dot() -> None:
    assert format_grams(2500) == "2.500 g" and format_grams(80.4) == "80 g" and format_grams(0) == "0 g"


def test_plan_consumption_splits_the_total_flour_by_blend_percentages() -> None:
    plan = {"ingredients": {"flour_g": 600}, "flours": [{"id": 1, "pct": 70}, {"id": 2, "pct": 30}]}
    assert plan_consumption(plan) == [(1, 420.0), (2, 180.0)]
    assert plan_consumption({**plan, "flours": [{"id": 1, "pct": 50}, {"id": 1, "pct": 50}]}) == [(1, 600.0)]


def test_plan_consumption_ignores_malformed_plans() -> None:
    assert plan_consumption(None) == [] and plan_consumption("x") == [] and plan_consumption({}) == []
    assert plan_consumption({"ingredients": {"flour_g": "600"}, "flours": [{"id": 1, "pct": 100}]}) == []
    assert plan_consumption({"ingredients": {"flour_g": -5}, "flours": [{"id": 1, "pct": 100}]}) == []
    assert plan_consumption({"ingredients": {"flour_g": 600}, "flours": [{"id": True, "pct": 100}]}) == []
    assert plan_consumption({"ingredients": {"flour_g": 600}, "flours": [{"id": 1, "pct": float("nan")}]}) == []
    assert plan_consumption({"ingredients": {"flour_g": 600}, "flours": ["x", {"id": "1", "pct": 100}]}) == []


def test_stock_can_be_set_added_and_cleared_and_rejects_bad_input(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await seed_if_empty()
        forte = (await _flour(sessions, "Forte 320")).id

        text = (await client.post(f"/farine/{forte}/scorta", data={"op": "set", "stock_g": "2500"})).text
        assert "2.500 g in dispensa" in text and "In dispensa" in text
        assert await _stock(sessions, "Forte 320") == 2500

        await client.post(f"/farine/{forte}/scorta", data={"op": "add", "stock_g": "5000"})
        assert await _stock(sessions, "Forte 320") == 7500

        assert "Scrivi quanti grammi" in (await client.post(f"/farine/{forte}/scorta", data={"op": "set"})).text
        await client.post(f"/farine/{forte}/scorta", data={"op": "set", "stock_g": "-50"})
        assert await _stock(sessions, "Forte 320") == 0  # i negativi diventano 0: finita
        await client.post(f"/farine/{forte}/scorta", data={"op": "set", "stock_g": "1e999"})
        assert await _stock(sessions, "Forte 320") == 0  # non finito: ignorato, resta com'era

        await client.post(f"/farine/{forte}/scorta", data={"op": "clear"})
        assert await _stock(sessions, "Forte 320") is None
        assert "non trovata" in (await client.post("/farine/9999/scorta", data={"op": "clear"})).text

    run_with_db(tmp_path, monkeypatch, check)


def test_flour_picker_lists_pantry_flours_first(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await seed_if_empty()
        before = (await client.get("/")).text
        assert 'optgroup label="In dispensa"' not in before

        forte = (await _flour(sessions, "Forte 320")).id
        await client.post(f"/farine/{forte}/scorta", data={"op": "set", "stock_g": "1000"})
        page = (await client.get("/")).text

        assert page.index('optgroup label="In dispensa"') < page.index('optgroup label="Agricola Piano"')
        assert "Agricola Piano · Forte 320" in page
        updated = (await client.post(f"/farine/{forte}/scorta", data={"op": "add", "stock_g": "1"})).text
        assert 'id="flourOptionsSource" hx-swap-oob="true"' in updated and 'optgroup label="In dispensa"' in updated

    run_with_db(tmp_path, monkeypatch, check)


def test_suggestions_are_limited_to_the_pantry_and_warn_when_flour_is_not_enough(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await seed_if_empty()
        base = {**_form(65), "mode": "guided", "strategy": "fridge_24"}
        everything = (await client.post("/plan", data=base)).text
        assert "Consigliate per questo impasto" in everything and "segnale in dispensa" in everything

        ids = {n: (await _flour(sessions, n)).id for n in ("Forte 320", "Suprema 410")}
        await client.post(f"/farine/{ids['Forte 320']}/scorta", data={"op": "set", "stock_g": "100"})
        text = (await client.post("/plan", data=base)).text

        assert "Consigliate tra quelle in dispensa" in text
        assert "Forte 320" in text and "Suprema 410" not in text.split("flourSuggest")[1].split("startInfo")[0]
        assert "In dispensa 100 g" in text and "non bastano da sole" in text

        await client.post(f"/farine/{ids['Forte 320']}/scorta", data={"op": "set", "stock_g": "5000"})
        enough = (await client.post("/plan", data=base)).text
        assert "In dispensa 5.000 g" in enough and "non bastano" not in enough

    run_with_db(tmp_path, monkeypatch, check)


def test_when_nothing_in_the_pantry_fits_the_others_are_shown_separately(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await seed_if_empty()
        generic = (await _flour(sessions, "Manitoba")).id  # Generica: mai consigliata
        await client.post(f"/farine/{generic}/scorta", data={"op": "set", "stock_g": "1000"})
        text = (await client.post("/plan", data={**_form(65), "mode": "guided", "strategy": "fridge_24"})).text
        block = text.split("flourSuggest")[1].split("startInfo")[0]

        assert "Nessuna delle farine in dispensa è adatta" in block
        assert "Non in dispensa, adatte a questo impasto" in block and block.count("useFlour(") >= 1
        assert "Consigliate tra quelle in dispensa" not in block

    run_with_db(tmp_path, monkeypatch, check)


def test_saving_a_trial_from_a_plan_takes_the_flour_out_of_the_pantry_once(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await seed_if_empty()
        forte, suprema = (await _flour(sessions, "Forte 320")).id, (await _flour(sessions, "Suprema 410")).id
        await client.post(f"/farine/{forte}/scorta", data={"op": "set", "stock_g": "1000"})
        await client.post(f"/farine/{suprema}/scorta", data={"op": "set", "stock_g": "200"})
        plan = {"ingredients": {"flour_g": 600}, "flours": [{"id": forte, "pct": 70}, {"id": suprema, "pct": 30}]}
        data = {"name": "Prova", "date": "2026-11-05", "plan_json": json.dumps(plan)}

        form = (await client.post("/diario/da-piano", data={**_form(65), "flour_id_0": str(forte), "flour_pct_0": "100"})).text
        assert 'name="use_stock" checked' in form

        saved = (await client.post("/diario", data={**data, "use_stock": "on"})).text
        assert "Scalato dalla dispensa" in saved and "Forte 320 −420 g (restano 580 g)" in saved
        assert await _stock(sessions, "Forte 320") == 580
        assert await _stock(sessions, "Suprema 410") == 20

        await client.post("/diario", data={**data, "name": "Seconda", "use_stock": "on"})
        assert await _stock(sessions, "Suprema 410") == 0  # mai sotto zero
        assert await _stock(sessions, "Forte 320") == 160

        await client.post("/diario", data={**data, "name": "Senza scalare"})  # casella non spuntata
        assert await _stock(sessions, "Forte 320") == 160

        async with sessions() as session:
            entry = await session.scalar(select(DiaryEntry).where(DiaryEntry.name == "Prova"))
            assert entry is not None
        edited = await client.post(f"/diario/{entry.id}", data={"name": "Prova modificata", "date": "2026-11-05"})
        assert edited.status_code == 200 and await _stock(sessions, "Forte 320") == 160  # le modifiche non scalano

    run_with_db(tmp_path, monkeypatch, check)


def test_flours_not_in_the_pantry_are_left_alone_when_a_trial_is_saved(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await seed_if_empty()
        forte = (await _flour(sessions, "Forte 320")).id
        data = {"name": "Prova", "date": "2026-11-05", "use_stock": "on", "plan_json": json.dumps(_plan(**{str(forte): 100}))}
        text = (await client.post("/diario", data=data)).text

        assert "Prova salvata nel diario." in text and "Scalato" not in text
        assert await _stock(sessions, "Forte 320") is None

    run_with_db(tmp_path, monkeypatch, check)
