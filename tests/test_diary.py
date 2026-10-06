"""Test delle rotte del Diario su un database SQLite temporaneo."""
from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from doughlab.db import Base
from doughlab.main import app
from doughlab.models import DiaryEntry, DiaryPhoto

from .test_backup import JPEG, data_url, sample_entry
from .test_main import _form

Check = Callable[[AsyncClient, async_sessionmaker], Awaitable[None]]


def run_with_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, check: Check) -> None:
    async def run() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'diary.sqlite3'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr("doughlab.diary.SessionLocal", sessions)
        monkeypatch.setattr("doughlab.recipes.SessionLocal", sessions)
        monkeypatch.setattr("doughlab.flours.SessionLocal", sessions)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await check(client, sessions)
        await engine.dispose()

    asyncio.run(run())


def backup_file(*entries: dict) -> dict:
    return {"file": ("backup.json", json.dumps({"entries": list(entries)}).encode(), "application/json")}


def test_entry_with_photo_is_saved_and_photo_is_served(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        response = await client.post(
            "/diario",
            data={"name": "Prova <b>1</b>", "date": "2026-10-06", "rating": "4", "hydration": "65,5"},
            files={"photo_main": ("foto.jpg", JPEG, "image/jpeg")},
        )
        assert response.status_code == 200
        assert "Prova salvata" in response.text
        assert "Prova <b>1</b>" not in response.text
        async with sessions() as session:
            entry = await session.scalar(select(DiaryEntry))
            assert entry is not None
            assert entry.hydration == 65.5
            assert entry.rating == 4
            photo = entry.photos[0]
        served = await client.get(f"/diario/foto/{photo.id}")
        assert served.content == JPEG
        assert served.headers["content-type"] == "image/jpeg"
        assert served.headers["x-content-type-options"] == "nosniff"

    run_with_db(tmp_path, monkeypatch, check)


def test_ready_before_start_shows_visible_error_and_keeps_values(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        response = await client.post(
            "/diario",
            data={
                "name": "Troppo presto",
                "date": "2026-10-06",
                "started_at": "2026-10-07T18:00",
                "ready_at": "2026-10-06T20:00",
                "notes": "da non perdere",
            },
        )
        assert 'class="diary-status error"' in response.text
        assert "non può essere pronto prima" in response.text
        assert "da non perdere" in response.text
        assert 'value="Troppo presto"' in response.text
        async with sessions() as session:
            assert await session.scalar(select(func.count(DiaryEntry.id))) == 0

    run_with_db(tmp_path, monkeypatch, check)


def test_only_start_without_ready_time_is_accepted(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        response = await client.post(
            "/diario",
            data={"name": "Solo inizio", "date": "2026-10-06", "started_at": "2026-10-07T18:00"},
        )
        assert "Prova salvata" in response.text

    run_with_db(tmp_path, monkeypatch, check)


def test_non_image_upload_is_rejected(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        response = await client.post(
            "/diario",
            data={"name": "Prova", "date": "2026-10-06"},
            files={"photo_main": ("foto.jpg", b"<svg onload=alert(1)>", "image/jpeg")},
        )
        assert "deve essere JPEG, PNG o WebP" in response.text
        async with sessions() as session:
            assert await session.scalar(select(func.count(DiaryEntry.id))) == 0

    run_with_db(tmp_path, monkeypatch, check)


def test_update_replaces_and_removes_photos_then_delete(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        await client.post(
            "/diario",
            data={"name": "Prova", "date": "2026-10-06"},
            files={"photo_main": ("a.jpg", JPEG, "image/jpeg")},
        )
        async with sessions() as session:
            entry = await session.scalar(select(DiaryEntry))
            assert entry is not None
            entry_id = entry.id

        edit = await client.get(f"/diario/{entry_id}/modifica")
        assert 'value="Prova"' in edit.text

        newer = JPEG + b"1"
        await client.post(
            f"/diario/{entry_id}",
            data={"name": "Prova 2", "date": "2026-10-06", "label_main": "Fetta"},
            files={"photo_extra1": ("b.jpg", newer, "image/jpeg")},
        )
        async with sessions() as session:
            entry = await session.scalar(select(DiaryEntry))
            assert entry is not None
            assert entry.name == "Prova 2"
            assert {p.slot for p in entry.photos} == {"main", "extra1"}

        await client.post(f"/diario/{entry_id}", data={"name": "Prova 2", "date": "2026-10-06", "remove_main": "1"})
        async with sessions() as session:
            assert await session.scalar(select(func.count(DiaryPhoto.id))) == 1

        await client.post(f"/diario/{entry_id}/elimina")
        async with sessions() as session:
            assert await session.scalar(select(func.count(DiaryEntry.id))) == 0
            assert await session.scalar(select(func.count(DiaryPhoto.id))) == 0

    run_with_db(tmp_path, monkeypatch, check)


def test_import_is_idempotent_and_never_overwrites_newer_local_edits(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        first = await client.post("/diario/importa", files=backup_file(sample_entry()))
        assert "1 nuove, 0 aggiornate, 0 già presenti" in first.text
        again = await client.post("/diario/importa", files=backup_file(sample_entry()))
        assert "0 nuove, 0 aggiornate, 1 già presenti" in again.text

        newer = sample_entry(name="Teglia rivista", updatedAt="2026-10-09T08:30:00.000Z")
        updated = await client.post("/diario/importa", files=backup_file(newer))
        assert "0 nuove, 1 aggiornate" in updated.text

        stale = await client.post("/diario/importa", files=backup_file(sample_entry()))
        assert "0 nuove, 0 aggiornate, 1 già presenti" in stale.text
        async with sessions() as session:
            entry = await session.scalar(select(DiaryEntry))
            assert entry is not None
            assert entry.name == "Teglia rivista"
            assert entry.oven == "Nettuno"
            assert len(entry.photos) == 1

    run_with_db(tmp_path, monkeypatch, check)


def test_export_then_import_into_empty_diary_is_lossless(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        extra = sample_entry(
            id="entry-2",
            name="Con extra",
            photos={"main": data_url(), "extra2": data_url(JPEG + b"2")},
            photoLabels={"extra2": "Alveolatura"},
        )
        await client.post("/diario/importa", files=backup_file(sample_entry(), extra))
        exported = (await client.get("/diario/export.json")).json()
        assert {e["id"] for e in exported["entries"]} == {"entry-1", "entry-2"}

        async with sessions() as session:
            for photo in await session.scalars(select(DiaryPhoto)):
                await session.delete(photo)
            for entry in await session.scalars(select(DiaryEntry)):
                await session.delete(entry)
            await session.commit()

        restore = {"file": ("b.json", json.dumps(exported).encode(), "application/json")}
        assert "2 nuove" in (await client.post("/diario/importa", files=restore)).text
        async with sessions() as session:
            by_name = {e.name: e for e in await session.scalars(select(DiaryEntry))}
            assert by_name["Con extra"].photos[1].label == "Alveolatura"
            assert by_name["Teglia 70%"].extra == {"customField": {"keep": True}}

    run_with_db(tmp_path, monkeypatch, check)


def test_import_rejects_non_backup_files(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        response = await client.post("/diario/importa", files={"file": ("x.json", b"nope", "text/plain")})
        assert "Importazione non riuscita" in response.text
        missing = await client.post("/diario/importa")
        assert "Scegli un file" in missing.text

    run_with_db(tmp_path, monkeypatch, check)


def test_plan_prefills_new_diary_entry(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        data = _form(68)
        data.update(preset_key="teglia", recipe_name="Teglia romana", oven_profile="split")
        data["phase_env_3"] = "fridge_home"
        response = await client.post("/diario/da-piano", data=data)

        assert response.status_code == 200
        assert "Nuova prova" in response.text
        assert 'value="Teglia romana"' in response.text
        assert 'name="hydration" value="68"' in response.text
        assert 'name="started_at" value="2026-10-03T11:00"' in response.text
        assert 'name="plan_json"' in response.text

        saved = await client.post(
            "/diario",
            data={"name": "Teglia romana", "date": "2026-10-03", "plan_json": json.dumps({"predicted_ready_at": "2026-10-03T20:00"})},
        )
        assert "Prova salvata" in saved.text
        async with sessions() as session:
            entry = await session.scalar(select(DiaryEntry))
            assert entry is not None
            assert entry.plan == {"predicted_ready_at": "2026-10-03T20:00"}

    run_with_db(tmp_path, monkeypatch, check)


def test_diary_shows_prediction_error_for_linked_plan(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        await client.post(
            "/diario",
            data={
                "name": "Confronto",
                "date": "2026-10-03",
                "started_at": "2026-10-03T10:00",
                "ready_at": "2026-10-04T11:30",
                "plan_json": json.dumps({"predicted_ready_at": "2026-10-04T10:00:00"}),
            },
        )
        page = await client.get("/")
        assert "Stima DoughLab 04/10 10:00, reale 04/10 11:30 (+1 h 30 min)" in page.text

    run_with_db(tmp_path, monkeypatch, check)


def test_out_of_range_ids_are_rejected_not_crashing(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        huge = "9" * 25
        for method, url in (
            ("GET", f"/diario/foto/{huge}"),
            ("POST", f"/diario/{huge}"),
            ("POST", f"/diario/{huge}/elimina"),
            ("GET", f"/diario?recipe={huge}"),
            ("POST", f"/ricette/{huge}/elimina"),
        ):
            assert (await client.request(method, url)).status_code == 422
        assert (await client.get("/diario/foto/5")).status_code == 404

    run_with_db(tmp_path, monkeypatch, check)


def test_service_worker_never_caches_dynamic_responses() -> None:
    from pathlib import Path

    source = (Path(__file__).parents[1] / "src/doughlab/static/sw.js").read_text()

    assert "startsWith('/static/')" in source
    assert "text/html" in source
