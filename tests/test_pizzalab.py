"""Test della lettura/scrittura dei backup di Pizza Lab."""
from __future__ import annotations

import base64
import json
from datetime import date
from typing import Any

import pytest

from doughlab.services.images import decode_data_url, sniff_image_mime
from doughlab.services.pizzalab import build_backup, parse_backup, parse_rating

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def data_url(payload: bytes = JPEG, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64,{base64.b64encode(payload).decode()}"


def sample_entry(**overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": "entry-1",
        "name": "Teglia 70%",
        "date": "2026-10-04",
        "pizzaType": "Teglia",
        "preferment": "Nessuno",
        "oven": "Nettuno",
        "flour": "Farina 00",
        "flourW": "260",
        "protein": "12,5",
        "hydration": "70",
        "coldHours": "24",
        "roomHours": "3",
        "doughBallCount": "4",
        "doughBallWeight": "250",
        "doughTemp": "24",
        "bakeTemp": "300",
        "bakeTime": "8 min",
        "bakeSetup": "Platea 300, cielo 200",
        "rating": "4.5",
        "ingredients": "Farina 500 g",
        "process": "Impasto, frigo",
        "bake": "Ripiano basso",
        "notes": "Buona",
        "nextChanges": "Meno sale",
        "tags": "teglia",
        "customField": {"keep": True},
        "photos": {"main": data_url(), "extra1": "", "extra2": "", "extra3": "", "extra4": ""},
        "photoLabels": {"extra1": "", "extra2": "", "extra3": "", "extra4": ""},
        "photoSettings": {"main": {"fit": "cover", "x": 0.2, "y": 0.8, "zoom": 2}},
        "updatedAt": "2026-10-05T08:30:00.000Z",
    }
    entry.update(overrides)
    return entry


def test_strings_become_numbers_and_text() -> None:
    result = parse_backup(json.dumps({"entries": [sample_entry()]}))
    entry = result.entries[0]

    assert result.warnings == []
    assert entry.external_id == "entry-1"
    assert entry.fields["name"] == "Teglia 70%"
    assert entry.fields["date"] == date(2026, 10, 4)
    assert entry.fields["protein"] == 12.5
    assert entry.fields["hydration"] == 70
    assert entry.fields["dough_ball_count"] == 4
    assert entry.fields["rating"] == 4.5
    assert entry.fields["oven"] == "Nettuno"
    assert entry.extra == {"customField": {"keep": True}}
    assert len(entry.photos) == 1
    assert entry.photos[0].data == JPEG
    assert entry.photos[0].settings["fit"] == "cover"
    assert entry.updated_at is not None


def test_hostile_or_empty_values_are_neutralised() -> None:
    hostile = sample_entry(
        name="  ",
        hydration="nan",
        coldHours="1e999",
        rating="0",
        flourW="abc",
        date="garbage",
        photos={"main": "data:image/jpeg;base64,@@@@", "extra1": data_url(b"<html>", "image/jpeg")},
    )
    entry = parse_backup(json.dumps([hostile])).entries[0]

    assert entry.fields["name"] == "Senza nome"
    assert entry.fields["hydration"] is None
    assert entry.fields["cold_hours"] is None
    assert entry.fields["rating"] is None
    assert entry.fields["flour_w"] is None
    assert entry.fields["date"] == date(2026, 10, 5)
    assert entry.photos == []


def test_invalid_photos_produce_warnings() -> None:
    result = parse_backup(json.dumps({"entries": [sample_entry(photos={"main": "data:x;base64,AA"})]}))

    assert any("main" in warning for warning in result.warnings)


@pytest.mark.parametrize("raw", ["not json", "{}", '{"entries": 3}', "42"])
def test_non_backup_files_are_rejected(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_backup(raw)


def test_round_trip_keeps_everything() -> None:
    entry = sample_entry()
    first = parse_backup(json.dumps({"entries": [entry]}))
    exported = build_backup(first.entries)["entries"][0]
    again = parse_backup(json.dumps({"entries": [exported]})).entries[0]

    assert exported["id"] == "entry-1"
    assert exported["customField"] == {"keep": True}
    assert exported["rating"] == "4.5"
    assert exported["photos"]["main"] == entry["photos"]["main"]
    assert exported["photos"]["extra1"] == ""
    assert again.fields == first.entries[0].fields
    assert again.photos[0].data == JPEG
    assert again.updated_at == first.entries[0].updated_at


def test_entries_without_id_get_unique_ids() -> None:
    raw = json.dumps({"entries": [sample_entry(id=""), sample_entry(id="")]})
    ids = {entry.external_id for entry in parse_backup(raw).entries}

    assert len(ids) == 2


@pytest.mark.parametrize(("value", "expected"), [("4.3", 4.5), ("0.2", None), ("9", 5.0), ("", None)])
def test_rating_is_rounded_to_half_points(value: str, expected: float | None) -> None:
    assert parse_rating(value) == expected


def test_image_type_is_decided_by_content_not_by_declared_type() -> None:
    assert sniff_image_mime(JPEG) == "image/jpeg"
    assert sniff_image_mime(b"<svg onload=alert(1)>") is None
    assert decode_data_url(data_url(b"<svg onload=alert(1)>", "image/jpeg")) is None
    assert decode_data_url("https://example.com/a.jpg") is None
