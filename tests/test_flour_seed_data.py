"""File dei dati delle farine: controllo del formato, correzioni agli archivi esistenti, data di verifica."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from doughlab.flours import format_verified, seed_if_empty, sync_builtin_seeds
from doughlab.models import AppSetting, Flour
from doughlab.services.flour_seed import FLOUR_SEEDS, SEED_REVISIONS, SEED_VERSION, load_seeds

from .test_diary import run_with_db

BASE = {"version": 1, "draft_note": "x"}


def write(tmp_path: Path, flours: list[dict]) -> Path:
    path = tmp_path / "seeds.json"
    path.write_text(json.dumps({**BASE, "flours": flours}))
    return path


def test_loader_rejects_malformed_flours(tmp_path: Path) -> None:
    ok = {"brand": "A", "name": "B"}
    assert load_seeds(write(tmp_path, [ok]))["flours"] == [ok]
    with pytest.raises(ValueError, match="senza nome"):
        load_seeds(write(tmp_path, [{"brand": "A"}]))
    with pytest.raises(ValueError, match="duplicata"):
        load_seeds(write(tmp_path, [ok, ok]))
    with pytest.raises(ValueError, match="sconosciuti"):
        load_seeds(write(tmp_path, [{**ok, "colore": "bianco"}]))
    with pytest.raises(ValueError, match="insieme"):
        load_seeds(write(tmp_path, [{**ok, "revised": 2}]))


def test_every_revision_is_not_newer_than_the_archive_and_changes_something() -> None:
    seeds = {(s["brand"], s["name"]): s for s in FLOUR_SEEDS}
    assert SEED_REVISIONS
    for key, (version, was) in SEED_REVISIONS.items():
        assert 1 < version <= SEED_VERSION and was
        assert any(seeds[key].get(field) != old for field, old in was.items()), key


def test_verified_dates_are_valid_and_shown_in_italian() -> None:
    assert format_verified("2026-11-05") == "il 5 novembre 2026"
    assert format_verified("2026-10") == "a ottobre 2026"
    assert format_verified("") == "" and format_verified("ieri") == "" and format_verified("2026-13") == ""
    for seed in FLOUR_SEEDS:
        if seed["brand"] != "Generica":
            assert format_verified(seed.get("verified", "")), seed["name"]


def test_sync_corrects_untouched_flours_and_keeps_the_ones_you_edited(tmp_path, monkeypatch) -> None:
    keys = {"vesuvio": ("Molino Vigevano", "Vesuvio"), "rossa": ("Le 5 Stagioni", "Pizza Napoletana Rossa"),
            "superiore": ("Le 5 Stagioni", "Superiore")}

    async def check(client, sessions) -> None:
        await seed_if_empty()
        async with sessions() as session:
            rows = {}
            for label, (brand, name) in keys.items():
                rows[label] = await session.scalar(select(Flour).where(Flour.brand == brand, Flour.name == name))
                for field, old in SEED_REVISIONS[(brand, name)][1].items():  # com'era prima della correzione
                    setattr(rows[label], field, old)
                rows[label].verified = ""
            rows["superiore"].w = 300  # l'hai corretta tu
            (await session.get(AppSetting, "flour_seed_version")).value = "6"
            await session.commit()

        await sync_builtin_seeds()
        assert await sync_builtin_seeds() == 0

        async with sessions() as session:
            vesuvio, rossa, superiore = [
                await session.scalar(select(Flour).where(Flour.brand == b, Flour.name == n)) for b, n in keys.values()
            ]
            assert vesuvio.pl == 0.65 and "P/L 0,6-0,7" in vesuvio.notes
            assert rossa.w == 310 and rossa.pl == 0.6 and "rev. 3" in rossa.notes
            assert superiore.w == 300  # tua: non sovrascritta
            assert "non riporta W e P/L" in superiore.notes  # le note restano com'erano
            assert vesuvio.verified == "2026-11-05" and rossa.verified == "2026-11-05"

    run_with_db(tmp_path, monkeypatch, check)


def test_flours_panel_shows_when_the_data_was_checked(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        await seed_if_empty()
        text = (await client.get("/farine")).text

        assert "Dati confrontati con la scheda del produttore il 5 novembre 2026." in text
        assert "a ottobre 2026" in text

    run_with_db(tmp_path, monkeypatch, check)


def test_link_check_reports_broken_and_moved_pages_but_not_reordered_parameters(monkeypatch) -> None:
    from doughlab.services import flour_links

    answers = {
        "https://a.it/x": (200, "", "https://a.it/x/"),
        "https://a.it/y": (404, "Not Found", "https://a.it/y"),
        "https://a.it/z": (200, "", "https://a.it/nuova"),
        "https://a.it/p?b=1&a=2": (200, "", "https://a.it/p?a=2&b=1"),
        "https://a.it/t": (None, "timed out", "https://a.it/t"),
    }
    monkeypatch.setattr(flour_links, "check_url", lambda url, timeout=0: answers[url])
    seeds = [{"brand": "A", "name": str(i), "source_url": url} for i, url in enumerate(answers)]
    seeds.append({"brand": "Generica", "name": "g", "source_url": ""})

    results = flour_links.check_links(seeds)

    assert [r.ok for r in results] == [True, False, True, True, False]
    assert [r.moved for r in results] == [False, False, True, False, False]
    assert len(results) == 5  # senza indirizzo https: saltata
