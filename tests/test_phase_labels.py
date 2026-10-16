"""Test del nome delle fasi di maturazione e dei valori automatici per condizione."""
from __future__ import annotations

from doughlab.planning import parse_phase_form
from doughlab.services.thermal import Environment

from .test_diary import run_with_db
from .test_main import _form


def _phase(kind: str, label: str, env: str) -> dict[str, str]:
    return {
        "phase_kind_0": kind, "phase_label_0": label, "phase_hours_0": "10", "phase_ambient_0": "20",
        "phase_container_0": "mass_bowl", "phase_env_0": env,
    }


def test_maturation_is_named_after_its_condition() -> None:
    ambient = parse_phase_form(_phase("maturation", "Maturazione in frigo", "ambient"))[0]
    chamber = parse_phase_form(_phase("maturation", "Maturazione", "chamber"))[0]
    fridge = parse_phase_form(_phase("maturation", "Maturazione a temperatura ambiente", "fridge_home"))[0]

    assert ambient.environment == Environment.AMBIENT and ambient.label == "Maturazione a temperatura ambiente"
    assert chamber.label == "Maturazione in cella"
    assert fridge.label == "Maturazione in frigo"


def test_custom_names_and_other_phases_are_left_alone() -> None:
    assert parse_phase_form(_phase("maturation", "La mia maturazione", "chamber"))[0].label == "La mia maturazione"
    assert parse_phase_form(_phase("proof", "Appretto", "fridge_home"))[0].label == "Appretto"


def test_plan_timeline_shows_the_chosen_condition_not_a_stale_label(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        data = {k: v for k, v in _form(65).items() if not k.startswith("phase_")}
        data.update(_phase("maturation", "Maturazione in frigo", "chamber"))

        text = (await client.post("/plan", data=data)).text

        assert "Maturazione in cella" in text and "Maturazione in frigo" not in text

    run_with_db(tmp_path, monkeypatch, check)


def test_phase_editor_updates_label_and_temperature_when_the_condition_changes(tmp_path, monkeypatch) -> None:
    async def check(client, sessions) -> None:
        page = (await client.get("/")).text

        assert page.count('onchange="applyEnvironment(this)"') >= 2  # schede e modello per le nuove fasi
        assert "function applyEnvironment(" in page and "function phaseLabelFor(" in page
        assert "room_c" in page and "fridge_c" in page.split("function environmentTemps")[1][:200]

    run_with_db(tmp_path, monkeypatch, check)
