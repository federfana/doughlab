"""Test delle farine: miscele, idratazione consigliata, dati predefiniti e rotte."""
from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from sqlalchemy import func, select

from doughlab.flours import backfill_builtin_methods, restore_builtin, seed_if_empty
from doughlab.models import Flour
from doughlab.services.flour_blend import (
    build_blend,
    estimate_hydration,
    hydration_position,
    method_warnings,
    parse_rows,
)
from doughlab.services.flour_seed import FLOUR_SEEDS

from .test_diary import run_with_db
from .test_main import _form


@dataclass
class F:
    id: int
    name: str
    brand: str = "X"
    w: float | None = None
    pl: float | None = None
    protein: float | None = None
    hydration_min: float | None = None
    hydration_max: float | None = None
    method: str = ""
    method_note: str = ""


def test_blend_uses_weighted_averages_and_normalises_percentages() -> None:
    blend = build_blend([(F(1, "a", w=260, protein=12), 60), (F(2, "b", w=380, protein=14), 40)])

    assert blend is not None
    assert blend.w == pytest.approx(308)
    assert blend.protein == pytest.approx(12.8)
    assert [round(c.share) for c in blend.components] == [60, 40]
    half = build_blend([(F(1, "a", w=300), 30), (F(2, "b", w=300), 30)])
    assert half is not None and half.entered_pct == 60
    assert [round(c.share) for c in half.components] == [50, 50]


def test_missing_values_are_averaged_only_over_the_flours_that_have_them() -> None:
    blend = build_blend([(F(1, "a", w=300), 50), (F(2, "b", w=None), 50)])

    assert blend is not None and blend.w == 300 and blend.protein is None and blend.pl is None


def test_hydration_advice_prefers_producer_data_and_falls_back_to_w() -> None:
    producer = build_blend([(F(1, "a", w=240, hydration_min=58, hydration_max=60), 100)])
    estimated = build_blend([(F(1, "a", w=240), 100)])
    mixed = build_blend([(F(1, "a", hydration_min=60, hydration_max=70), 50), (F(2, "b", w=240), 50)])
    nothing = build_blend([(F(1, "a", protein=12), 100)])

    assert producer and producer.hydration and producer.hydration.basis == "produttore"
    assert (producer.hydration.low, producer.hydration.high) == (58, 60)
    assert estimated and estimated.hydration and estimated.hydration.basis == "stima dalla forza W"
    assert mixed and mixed.hydration and mixed.hydration.basis == "mista"
    assert (mixed.hydration.low, mixed.hydration.high) == (59, 66)
    assert nothing and nothing.hydration is None


def test_estimated_hydration_grows_with_flour_strength() -> None:
    spans = [estimate_hydration(w) for w in (180, 240, 290, 330, 360, 420)]

    assert all(a[0] <= b[0] and a[1] <= b[1] for a, b in zip(spans, spans[1:], strict=False))
    assert estimate_hydration(240) == (58, 62)


def test_hydration_position_has_half_point_tolerance() -> None:
    blend = build_blend([(F(1, "a", hydration_min=60, hydration_max=65), 100)])
    assert blend and blend.hydration
    assert hydration_position(blend.hydration, 59.6) == "dentro"
    assert hydration_position(blend.hydration, 58) == "sotto"
    assert hydration_position(blend.hydration, 66) == "sopra"


def test_rows_ignore_invalid_duplicate_and_excess_entries() -> None:
    data = {
        "flour_id_0": "5", "flour_pct_0": "60,5",
        "flour_id_1": "5", "flour_pct_1": "10",
        "flour_id_2": "abc", "flour_pct_2": "30",
    }
    assert parse_rows(data) == [(5, 60.5)]
    assert parse_rows({"flour_id_0": "7", "flour_pct_0": "nan"}) == []
    assert parse_rows({"flour_id_0": "9" * 30, "flour_pct_0": "50"}) == []


def test_builtin_data_is_consistent_and_covers_the_requested_producers() -> None:
    keys = [(s["brand"], s["name"]) for s in FLOUR_SEEDS]
    assert len(keys) == len(set(keys))
    brands = {b for b, _ in keys}
    assert {"Agricola Piano", "Molino Caputo", "Molino Casillo", "Le Farine Magiche",
            "Molino Vigevano", "Generica"} <= brands
    for seed in FLOUR_SEEDS:
        low, high = seed.get("hydration_min"), seed.get("hydration_max")
        assert (low is None) == (high is None)
        if low is not None:
            assert low <= high
        if seed["brand"] != "Generica":
            assert seed["source_url"].startswith("https://")
        assert seed.get("w") is None or 100 <= seed["w"] <= 500


def test_seed_runs_once_and_restore_adds_only_missing_ones(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await seed_if_empty()
        await seed_if_empty()
        async with sessions() as session:
            assert await session.scalar(select(func.count(Flour.id))) == len(FLOUR_SEEDS)
            await session.delete(await session.scalar(select(Flour).where(Flour.name == "Nuvola")))
            await session.commit()
        await seed_if_empty()
        async with sessions() as session:
            assert await session.scalar(select(func.count(Flour.id))) == len(FLOUR_SEEDS) - 1
        assert await restore_builtin() == 1
        assert await restore_builtin() == 0

    run_with_db(tmp_path, monkeypatch, check)


def test_flour_crud_validation_and_search(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await seed_if_empty()
        page = (await client.get("/farine")).text
        assert "Molino Caputo" in page and "Agricola Piano" in page
        assert "Nessuna farina corrisponde" in (await client.get("/farine?q=zzzz")).text
        assert "Forte 320" in (await client.get("/farine?q=agricola forte")).text

        assert "Dai un nome" in (await client.post("/farine", data={"brand": "X"})).text
        one_sided = await client.post("/farine", data={"name": "Mia", "hydration_min": "60"})
        assert "entrambi gli estremi" in one_sided.text
        reversed_range = await client.post("/farine", data={"name": "Mia", "hydration_min": "70", "hydration_max": "60"})
        assert "non può superare" in reversed_range.text

        created = await client.post(
            "/farine",
            data={"brand": "Mulino <b>Mio</b>", "name": "Speciale", "w": "310", "pl": "0,55", "protein": "13,2",
                  "hydration_min": "62", "hydration_max": "68"},
        )
        assert "salvata" in created.text and "<b>Mio</b>" not in created.text
        duplicate = await client.post("/farine", data={"brand": "Mulino <b>Mio</b>", "name": "Speciale"})
        assert "Esiste già" in duplicate.text

        async with sessions() as session:
            flour = await session.scalar(select(Flour).where(Flour.name == "Speciale"))
            assert flour is not None and (flour.w, flour.pl, flour.protein) == (310, 0.55, 13.2)
            flour_id = flour.id
        assert 'value="Speciale"' in (await client.get(f"/farine/{flour_id}/modifica")).text
        await client.post(f"/farine/{flour_id}", data={"brand": "Mio", "name": "Speciale", "w": "320"})
        await client.post(f"/farine/{flour_id}/elimina")
        async with sessions() as session:
            assert await session.scalar(select(Flour).where(Flour.name == "Speciale")) is None

    run_with_db(tmp_path, monkeypatch, check)


async def _id_of(sessions, name: str) -> int:
    async with sessions() as session:
        flour = await session.scalar(select(Flour).where(Flour.name == name))
        assert flour is not None
        return flour.id


def test_plan_shows_blend_stats_and_hydration_advice(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await seed_if_empty()
        nuvola, forte = await _id_of(sessions, "Nuvola"), await _id_of(sessions, "Forte 320")
        data = _form(55)
        data.update(flour_id_0=str(nuvola), flour_pct_0="60", flour_id_1=str(forte), flour_pct_1="40")
        text = (await client.post("/plan", data=data)).text

        assert "Molino Caputo Nuvola: 60%" in text and "Agricola Piano Forte 320: 40%" in text
        assert "W circa 310" in text
        assert "Idratazione consigliata" in text and "sotto l'intervallo" in text
        assert "useHydration(" in text

        inside = _form(66)
        inside.update(flour_id_0=str(forte), flour_pct_0="100")
        assert "nell'intervallo consigliato" in (await client.post("/plan", data=inside)).text

        assert "Idratazione consigliata" not in (await client.post("/plan", data=_form(65))).text

    run_with_db(tmp_path, monkeypatch, check)


def test_blend_prefills_diary_and_is_saved_with_the_recipe(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await seed_if_empty()
        forte = await _id_of(sessions, "Forte 320")
        data = _form(66)
        data.update(flour_id_0=str(forte), flour_pct_0="100", preset_key="teglia", save_name="Con farina")

        diary = (await client.post("/diario/da-piano", data=data)).text
        assert 'name="flour" value="Agricola Piano Forte 320"' in diary
        assert 'name="flour_w" value="355"' in diary
        assert 'name="protein" value="13"' in diary
        assert json.loads(json.dumps({"ok": 1}))  # il piano resta serializzabile

        await client.post("/ricette", data=data)
        reopened = (await client.get("/?recipe=1")).text
        assert f'<option value="{forte}" selected>' in reopened
        assert 'name="flour_pct_0" value="100"' in reopened

    run_with_db(tmp_path, monkeypatch, check)


def test_planner_lists_flours_in_a_selector_and_has_the_manager(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await seed_if_empty()
        page = (await client.get("/")).text
        assert '<optgroup label="Molino Vigevano">' in page
        assert 'id="tab-flours"' in page and 'id="panel-flours"' in page
        assert 'id="floursPanel"' in page
        assert "Le mie farine" not in page
        assert 'id="flourOptionsSource" hidden' in page

    run_with_db(tmp_path, monkeypatch, check)


def test_flour_changes_refresh_the_planner_options_out_of_band(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await seed_if_empty()
        created = (await client.post("/farine", data={"brand": "Nuovo Mulino", "name": "Farina Nuova"})).text

        assert 'id="flourOptionsSource" hx-swap-oob="true"' in created
        assert '<optgroup label="Nuovo Mulino">' in created

    run_with_db(tmp_path, monkeypatch, check)


def test_method_warnings_only_for_exclusive_declarations() -> None:
    direct = build_blend([(F(1, "a", method="diretto"), 100)])
    indirect = build_blend([(F(2, "b", method="indiretto"), 100)])
    both = build_blend([(F(3, "c", method="entrambi"), 100)])
    unknown = build_blend([(F(4, "d", method_note="Ottima per bighe"), 100)])

    assert direct and indirect and both and unknown
    assert method_warnings(direct, has_preferment=True) and not method_warnings(direct, has_preferment=False)
    assert method_warnings(indirect, has_preferment=False) and not method_warnings(indirect, has_preferment=True)
    for blend in (both, unknown):
        assert not method_warnings(blend, True) and not method_warnings(blend, False)


def test_agricola_piano_flours_all_declare_direct_or_indirect_use() -> None:
    declared = {s["name"]: s["method"] for s in FLOUR_SEEDS if s["brand"] == "Agricola Piano"}

    assert len(declared) == 8 and all(declared.values())
    assert declared["Profumata 240"] == declared["Rustica 210"] == "diretto"
    assert declared["Forte 320"] == "entrambi"
    assert all(s["method"] in {"", "diretto", "indiretto", "entrambi"} for s in FLOUR_SEEDS)


def test_flour_form_saves_method_and_ignores_unknown_values(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await client.post("/farine", data={"name": "A", "method": "diretto", "method_note": "Solo diretto"})
        await client.post("/farine", data={"name": "B", "method": "<script>"})
        async with sessions() as session:
            a = await session.scalar(select(Flour).where(Flour.name == "A"))
            b = await session.scalar(select(Flour).where(Flour.name == "B"))
            assert a is not None and (a.method, a.method_note) == ("diretto", "Solo diretto")
            assert b is not None and b.method == ""
        page = (await client.get("/farine")).text
        assert "Impasto: solo diretto" in page and "Solo diretto»" in page

    run_with_db(tmp_path, monkeypatch, check)


def test_plan_warns_when_exclusive_direct_flour_meets_a_preferment(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await seed_if_empty()
        profumata = await _id_of(sessions, "Profumata 240")
        direct = _form(62)
        direct.update(flour_id_0=str(profumata), flour_pct_0="100")
        text = (await client.post("/plan", data=direct)).text
        assert "solo diretto" in text and "usa un prefermento" not in text

        indirect = dict(direct, preferment_pct="30")
        assert "indicata solo per impasti diretti, ma il piano usa un prefermento" in (
            await client.post("/plan", data=indirect)
        ).text

        forte = await _id_of(sessions, "Forte 320")
        both = dict(indirect, flour_id_0=str(forte))
        text = (await client.post("/plan", data=both)).text
        assert "diretto o indiretto" in text and "usa un prefermento" not in text

    run_with_db(tmp_path, monkeypatch, check)


def test_backfill_fills_builtin_methods_without_overwriting_user_data(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await seed_if_empty()
        async with sessions() as session:
            for flour in await session.scalars(select(Flour)):
                flour.method, flour.method_note = "", ""
            mine = await session.scalar(select(Flour).where(Flour.name == "Profumata 290"))
            assert mine is not None
            mine.method_note = "mia nota"
            await session.commit()
        await backfill_builtin_methods()
        async with sessions() as session:
            versatile = await session.scalar(select(Flour).where(Flour.name == "Versatile 240"))
            kept = await session.scalar(select(Flour).where(Flour.name == "Profumata 290"))
            assert versatile is not None and versatile.method == "diretto"
            assert kept is not None and kept.method == "" and kept.method_note == "mia nota"

    run_with_db(tmp_path, monkeypatch, check)
