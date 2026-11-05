"""Impasto in corso sul server: sincronizzazione, lapide, controllo dei dati e promemoria per il Calendario."""
from __future__ import annotations

import json
import time

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from doughlab.services.live_state import clean_live_state, live_reminders_ics, phase_ends

from .test_diary import run_with_db


def now_ms() -> int:
    return int(time.time() * 1000)


def state(started: int | None = None, **changes) -> dict:
    started = started or now_ms() - 60_000
    base = {
        "name": "Napoletana, del sabato", "startedAt": started,
        "phases": [{"kind": "mix", "label": "Impasto", "hours": 0.5}, {"kind": "bulk", "label": "Puntata", "hours": 2},
                   {"kind": "bake", "label": "Cottura", "hours": 0}],
        "actual": [started], "extra": [0, 15, 0], "checks": {"0:1": True}, "notified": {}, "doughTemp": "24",
        "plannedReady": "2026-11-06T01:00:00",
    }
    return {**base, **changes}


def test_clean_live_state_keeps_the_known_fields_and_rejects_nonsense() -> None:
    cleaned = clean_live_state({**state(), "intruso": "x", "name": "N" * 500})

    assert cleaned is not None and "intruso" not in cleaned and len(cleaned["name"]) == 120
    assert clean_live_state(None) is None and clean_live_state({"phases": []}) is None
    assert clean_live_state(state(phases=[{"kind": "a", "label": "b", "hours": float("nan")}])) is None
    assert clean_live_state(state(phases=[{"kind": "a", "label": "b", "hours": 9999}])) is None
    assert clean_live_state(state(actual=[])) is None and clean_live_state(state(actual=["x"])) is None
    assert clean_live_state(state(startedAt=True)) is None
    assert clean_live_state(state(checks=[1])) is None
    assert clean_live_state(state(phases=[{"kind": "a", "label": "b", "hours": 1}] * 61)) is None


def test_phase_ends_follow_the_current_phase_and_the_adjustments() -> None:
    started = 1_000_000_000_000
    ends = phase_ends(state(started, actual=[started - 600_000, started]))

    assert [index for index, _ in ends] == [1, 2]
    assert ends[0][1] == started + (2 * 60 + 15) * 60_000  # 2 h + 15 min di scarto
    assert phase_ends(state(started, actual=[started] * 4)) == []  # tutte concluse


def test_reminders_have_one_alarm_per_remaining_phase_with_stable_ids() -> None:
    now = now_ms()
    ics = live_reminders_ics(clean_live_state(state(now - 60_000)), 5_000, now)

    assert ics is not None and ics.endswith("\r\n") and ics.count("BEGIN:VEVENT") == 2  # Cottura (0 min) saltata
    assert ics.count("BEGIN:VALARM") == 2 and "TRIGGER:PT0S" in ics
    assert "Napoletana\\, del sabato" in ics and "Impasto finita → ora Puntata" in ics
    assert f"UID:doughlab-live-{now - 60_000}-0@doughlab.local" in ics and "SEQUENCE:5\r\n" in ics
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))
    assert live_reminders_ics(clean_live_state(state(now - 99_999_999_999)), 1, now) is None  # tutto già passato


def test_live_state_is_stored_on_the_server_and_older_writes_lose(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        assert (await client.get("/live")).json() == {"savedAt": 0, "state": None}

        saved = await client.put("/live", json={"savedAt": 2000, "state": state()})
        assert saved.status_code == 200 and saved.json()["savedAt"] == 2000
        stored = (await client.get("/live")).json()
        assert stored["savedAt"] == 2000 and stored["state"]["name"] == "Napoletana, del sabato"

        older = await client.put("/live", json={"savedAt": 1000, "state": state(name="vecchio")})
        assert older.status_code == 409 and older.json()["state"]["name"] == "Napoletana, del sabato"
        newer = await client.put("/live", json={"savedAt": 3000, "state": state(name="nuovo")})
        assert newer.status_code == 200 and (await client.get("/live")).json()["state"]["name"] == "nuovo"

    run_with_db(tmp_path, monkeypatch, check)


def test_closing_leaves_a_tombstone_so_an_old_copy_cannot_come_back(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        await client.put("/live", json={"savedAt": 2000, "state": state()})
        closed = await client.put("/live", json={"savedAt": 5000, "state": None})

        assert closed.status_code == 200 and (await client.get("/live")).json() == {"savedAt": 5000, "state": None}
        stale = await client.put("/live", json={"savedAt": 2500, "state": state()})  # un altro dispositivo, rimasto indietro
        assert stale.status_code == 409 and (await client.get("/live")).json()["state"] is None

    run_with_db(tmp_path, monkeypatch, check)


def test_live_endpoint_rejects_bad_requests(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        bad = [
            {"savedAt": 1000, "state": {"phases": []}},
            {"savedAt": "x", "state": state()},
            {"savedAt": -5, "state": state()},
            {"savedAt": True, "state": state()},
            {"state": state()},
            [],
        ]
        for body in bad:
            assert (await client.put("/live", json=body)).status_code == 400, body
        assert (await client.put("/live", content=b"non json")).status_code == 400
        huge = json.dumps({"savedAt": 1000, "state": state(), "x": "a" * 200_000})
        assert (await client.put("/live", content=huge)).status_code == 413
        assert (await client.get("/live")).json() == {"savedAt": 0, "state": None}

    run_with_db(tmp_path, monkeypatch, check)


def test_calendar_download_uses_the_server_copy(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        assert (await client.get("/live/calendar.ics")).status_code == 404

        await client.put("/live", json={"savedAt": now_ms(), "state": state()})
        response = await client.get("/live/calendar.ics")
        assert response.status_code == 200 and response.headers["content-type"].startswith("text/calendar")
        assert "doughlab-promemoria.ics" in response.headers["content-disposition"]
        assert response.text.count("BEGIN:VEVENT") == 2

        await client.put("/live", json={"savedAt": now_ms() + 10, "state": None})
        assert (await client.get("/live/calendar.ics")).status_code == 404

    run_with_db(tmp_path, monkeypatch, check)


def test_page_syncs_live_state_and_offers_the_calendar(tmp_path, monkeypatch) -> None:
    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        page = (await client.get("/")).text

        assert "fetch('/live'" in page and "livePull()" in page and "livePush()" in page
        assert "liveCalendar()" in page and "/live/calendar.ics" in page

    run_with_db(tmp_path, monkeypatch, check)
