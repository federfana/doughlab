"""Test dell'aggiunta automatica delle colonne mancanti."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, String, inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase

from doughlab import db


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prepare: str, model_columns: list[Column]):
    class Base(DeclarativeBase):
        pass

    from sqlalchemy import Table

    Table("things", Base.metadata, Column("id", Integer, primary_key=True), *model_columns)
    monkeypatch.setattr(db, "Base", Base)

    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'm.sqlite3'}")
        try:
            async with engine.begin() as connection:
                await connection.execute(text(prepare))
                await connection.execute(text("INSERT INTO things (id, name) VALUES (1, 'a')"))
            async with engine.begin() as connection:
                added = await connection.run_sync(db._add_missing_columns)
                row = (await connection.execute(text("SELECT * FROM things"))).mappings().one()
                columns = await connection.run_sync(
                    lambda c: [x["name"] for x in inspect(c).get_columns("things")]
                )
        finally:
            await engine.dispose()
        return added, dict(row), columns

    return asyncio.run(run())


def test_missing_columns_are_added_with_defaults_and_old_rows_survive(tmp_path, monkeypatch) -> None:
    added, row, columns = _run(
        tmp_path,
        monkeypatch,
        "CREATE TABLE things (id INTEGER PRIMARY KEY, name VARCHAR(20))",
        [
            Column("name", String(20)),
            Column("method", String(12), nullable=False, default="x'y"),
            Column("score", Integer, nullable=True),
            Column("flag", Integer, nullable=False, default=1),
        ],
    )

    assert added == {("things", "method"), ("things", "score"), ("things", "flag")}
    assert row == {"id": 1, "name": "a", "method": "x'y", "score": None, "flag": 1}
    assert set(columns) == {"id", "name", "method", "score", "flag"}


def test_nothing_to_add_returns_empty_set(tmp_path, monkeypatch) -> None:
    added, row, _ = _run(
        tmp_path, monkeypatch,
        "CREATE TABLE things (id INTEGER PRIMARY KEY, name VARCHAR(20))",
        [Column("name", String(20))],
    )

    assert added == set() and row["name"] == "a"


def test_new_not_null_column_without_a_simple_default_is_refused(tmp_path, monkeypatch) -> None:
    with pytest.raises(RuntimeError, match="valore predefinito"):
        _run(
            tmp_path, monkeypatch,
            "CREATE TABLE things (id INTEGER PRIMARY KEY, name VARCHAR(20))",
            [Column("name", String(20)), Column("must", String(5), nullable=False)],
        )
