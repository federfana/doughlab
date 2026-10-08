"""Test delle farine consigliate e dell'allineamento dell'archivio predefinito."""
from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import func, select

from doughlab.flours import seed_if_empty, sync_builtin_seeds
from doughlab.models import AppSetting, Flour
from doughlab.services.flour_seed import DRAFT_NOTE, FLOUR_SEEDS, SEED_SINCE
from doughlab.services.flour_suggest import suggest_flours, target_w

from .test_diary import run_with_db
from .test_main import _form


@dataclass
class F:
    id: int
    name: str
    brand: str = "Marca"
    kind: str = "Tipo 0"
    w: float | None = None
    pl: float | None = None
    protein: float | None = None
    hydration_min: float | None = None
    hydration_max: float | None = None
    method: str = ""
    method_note: str = ""


def _names(flours: list[F], **kwargs: object) -> list[str]:
    options: dict[str, object] = dict(style="napoletana", total_hours=24, hydration_pct=65, has_preferment=False)
    options.update(kwargs)
    return [s.flour.name for s in suggest_flours(flours, **options)]  # type: ignore[arg-type]


def test_target_w_grows_with_time_hydration_and_heavy_styles() -> None:
    assert target_w(8, 62, "napoletana") == (220, 280)
    assert target_w(24, 62, "napoletana") == (260, 320)
    assert target_w(72, 62, "napoletana") == (320, 380)
    assert target_w(24, 80, "teglia") == (310, 370)


def test_suggestions_prefer_the_flour_whose_w_fits_the_plan() -> None:
    flours = [F(1, "debole", w=200), F(2, "giusta", w=290), F(3, "troppo forte", w=420)]

    assert _names(flours, total_hours=24)[0] == "giusta"
    assert _names(flours, total_hours=8, hydration_pct=58)[0] in {"giusta", "debole"}


def test_generic_integral_and_method_mismatches_are_not_suggested() -> None:
    flours = [
        F(1, "generica", brand="Generica", w=290),
        F(2, "integrale", kind="Integrale", w=290),
        F(3, "solo diretto", w=290, method="diretto"),
        F(4, "solo indiretto", w=290, method="indiretto"),
        F(5, "va bene", w=290),
    ]

    assert set(_names(flours, has_preferment=False)) == {"va bene", "solo diretto"}
    assert set(_names(flours, has_preferment=True)) == {"va bene", "solo indiretto"}
    assert "integrale" in _names(flours, style="pane")


def test_different_brands_come_first_and_flours_without_w_are_skipped() -> None:
    flours = [
        F(1, "a1", brand="A", w=290), F(2, "a2", brand="A", w=292), F(3, "b1", brand="B", w=285),
        F(4, "senza W", brand="C"),
    ]

    names = [
        s.flour.name
        for s in suggest_flours(
            flours, style="napoletana", total_hours=24, hydration_pct=65, has_preferment=False, limit=2
        )
    ]
    assert {n[0] for n in names} == {"a", "b"}
    assert "senza W" not in _names(flours)


def test_nothing_is_suggested_when_no_flour_fits_and_reasons_explain_the_choice() -> None:
    assert _names([F(1, "troppo debole", w=120)], total_hours=72, hydration_pct=80) == []

    reason = suggest_flours(
        [F(1, "x", w=290, hydration_min=60, hydration_max=70)],
        style="napoletana", total_hours=24, hydration_pct=65, has_preferment=False,
    )[0].reason
    assert "W 290" in reason and "260-320" in reason and "range del produttore 60-70%" in reason


def test_added_flours_carry_producer_data_and_no_third_party_note() -> None:
    added = {(s["brand"], s["name"]): s for s in FLOUR_SEEDS if (s["brand"], s["name"]) in SEED_SINCE}

    assert ("Le 5 Stagioni", "Superiore") in added and ("Polselli", "Vivace") in added
    assert ("Molino Quaglia", "Petra 5037") in added and ("Pastificio Garofalo", "Farina W 350") in added
    for seed in added.values():
        assert "MakeMyPizza" not in seed["notes"] + seed["source_url"]
        assert seed["source_url"].startswith("https://") and seed["notes"]
    # Dove il produttore non esprime W e P/L, restano vuoti invece di essere inventati.
    assert added[("Le 5 Stagioni", "Superiore")].get("w") is None
    assert added[("Molino Quaglia", "Petra 3")].get("pl") is None


def test_sync_adds_new_seeds_once_fills_gaps_and_respects_user_choices(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await seed_if_empty()
        async with sessions() as session:
            # Simula un archivio di prima della versione 2.
            await session.delete(await session.get(AppSetting, "flour_seed_version"))
            for flour in await session.scalars(select(Flour).where(Flour.brand.in_(["Le 5 Stagioni", "Polselli"]))):
                await session.delete(flour)
            polselli_gone = len(SEED_SINCE)  # tutte le nuove, tranne quelle di altre marche, restano
            nuvola = await session.scalar(select(Flour).where(Flour.name == "Nuvola"))
            assert nuvola is not None
            nuvola.pl = None
            casillo = await session.scalar(select(Flour).where(Flour.name == "Zero M"))
            assert casillo is not None
            casillo.protein = 99
            mine = Flour(brand="Mia", name="Mia farina", w=None, builtin=False)
            session.add(mine)
            deleted = await session.scalar(select(Flour).where(Flour.name == "Aria"))
            assert deleted is not None
            await session.delete(deleted)
            await session.commit()
        assert polselli_gone == 8

        assert await sync_builtin_seeds() == 3 + 1
        assert await sync_builtin_seeds() == 0

        async with sessions() as session:
            names = set(await session.scalars(select(Flour.name)))
            assert {"Superiore", "Pizza Napoletana Rossa", "Mora", "Vivace"} <= names
            assert "Aria" not in names  # le eliminate non tornano
            refilled = await session.scalar(select(Flour).where(Flour.name == "Nuvola"))
            assert refilled is not None and refilled.pl == 0.55
            kept = await session.scalar(select(Flour).where(Flour.name == "Zero M"))
            assert kept is not None and kept.protein == 99
            own = await session.scalar(select(Flour).where(Flour.name == "Mia farina"))
            assert own is not None and own.w is None

    run_with_db(tmp_path, monkeypatch, check)


def test_sync_corrects_untouched_draft_flours_and_leaves_edited_ones(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await seed_if_empty()
        async with sessions() as session:
            for flour in await session.scalars(select(Flour).where(Flour.name.in_(["Pizza Napoletana Rossa", "Petra 5037"]))):
                await session.delete(flour)
            session.add_all([
                Flour(brand="Le 5 Stagioni", name="Pizza Napoletana", kind="Tipo 00", w=300, pl=0.6, protein=13,
                      notes=DRAFT_NOTE, source_url="https://makemypizza.ai.studio/", builtin=True),
                Flour(brand="Molino Quaglia", name="Petra 5037 Speciale Pizza", kind="Tipo 0", w=320, pl=0.55,
                      protein=13.5, notes="la mia nota", builtin=True),
            ])
            await session.delete(await session.get(AppSetting, "flour_seed_version"))
            session.add(AppSetting(key="flour_seed_version", value="3"))  # già alla versione corrente
            await session.commit()

        await sync_builtin_seeds()
        assert await sync_builtin_seeds() == 0

        async with sessions() as session:
            names = set(await session.scalars(select(Flour.name)))
            assert "Pizza Napoletana" not in names and "Pizza Napoletana Rossa" in names
            fixed = await session.scalar(select(Flour).where(Flour.name == "Pizza Napoletana Rossa"))
            assert fixed is not None and fixed.w is None and fixed.pl is None and fixed.protein == 13
            assert "MakeMyPizza" not in fixed.notes + fixed.source_url and fixed.source_url.startswith("https://le5stagioni")
            mine = await session.scalar(select(Flour).where(Flour.name == "Petra 5037 Speciale Pizza"))
            assert mine is not None and mine.notes == "la mia nota" and mine.w == 320

    run_with_db(tmp_path, monkeypatch, check)


def test_fresh_database_is_seeded_at_the_current_version_and_sync_does_nothing(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await seed_if_empty()
        assert await sync_builtin_seeds() == 0
        async with sessions() as session:
            assert await session.scalar(select(func.count(Flour.id))) == len(FLOUR_SEEDS)

    run_with_db(tmp_path, monkeypatch, check)


def test_plan_response_lists_suggested_flours_with_a_use_button(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await seed_if_empty()
        base = {**_form(65), "mode": "guided", "strategy": "fridge_24"}
        text = (await client.post("/plan", data=base)).text

        assert 'id="flourSuggest" hx-swap-oob="innerHTML"' in text
        assert "Consigliate per questo impasto" in text
        assert text.count("useFlour(") >= 1

        picked = text.split("useFlour(")[1].split(")")[0]
        chosen = await client.post("/plan", data={**base, "flour_id_0": picked, "flour_pct_0": "100"})
        assert "in uso" in chosen.text

    run_with_db(tmp_path, monkeypatch, check)


def test_planner_page_has_a_reset_and_mode_dependent_controls(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        page = (await client.get("/")).text

        assert "resetPlan()" in page and 'id="flourSuggest"' in page
        assert "Guidata: scegli strategia" in page and "Esperto: controlli tu" in page
        assert "kind !== 'none' && mode === 'expert'" in page
        assert '<details class="panel" x-show="mode === \'expert\'"' in page

    run_with_db(tmp_path, monkeypatch, check)


@pytest.mark.parametrize("hours", [8, 24, 48, 72])
def test_suggestions_never_crash_on_the_real_seed(hours: int) -> None:
    flours = [F(i, s["name"], brand=s["brand"], kind=s.get("kind", ""), w=s.get("w"),
                hydration_min=s.get("hydration_min"), hydration_max=s.get("hydration_max"),
                method=s.get("method", "")) for i, s in enumerate(FLOUR_SEEDS)]

    found = suggest_flours(flours, style="napoletana", total_hours=hours, hydration_pct=65, has_preferment=False)

    assert len(found) <= 3 and all(s.flour.brand != "Generica" for s in found)
