"""Copia giornaliera del database: coerente, una al giorno, con rotazione."""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from doughlab.services.db_backup import backup_database, rotate_backups, sqlite_path


def make_db(path: Path, value: str = "uno") -> Path:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
        connection.execute("DELETE FROM t")
        connection.execute("INSERT INTO t VALUES (?)", (value,))
    return path


def read(path: Path) -> list[str]:
    with sqlite3.connect(path) as connection:
        return [row[0] for row in connection.execute("SELECT v FROM t")]


def test_sqlite_path_only_for_sqlite_files() -> None:
    assert sqlite_path("sqlite+aiosqlite:////tmp/x/doughlab.db") == Path("/tmp/x/doughlab.db")
    assert sqlite_path("sqlite+aiosqlite:///:memory:") is None
    assert sqlite_path("postgresql://u@h/db") is None


def test_backup_is_a_consistent_copy_made_once_per_day(tmp_path: Path) -> None:
    source = make_db(tmp_path / "doughlab.db", "uno")
    folder = tmp_path / "backups"

    first = backup_database(source, folder, today=date(2026, 11, 5))
    make_db(source, "due")

    assert first == folder / "doughlab-2026-11-05.db" and read(first) == ["uno"]
    assert backup_database(source, folder, today=date(2026, 11, 5)) is None  # già fatta oggi
    assert read(first) == ["uno"]
    second = backup_database(source, folder, today=date(2026, 11, 6))
    assert second is not None and read(second) == ["due"]
    assert not list(folder.glob("*.partial"))


def test_backup_skips_a_missing_database_and_cleans_up_on_failure(tmp_path: Path) -> None:
    folder = tmp_path / "backups"
    assert backup_database(tmp_path / "manca.db", folder) is None and not folder.exists()

    broken = tmp_path / "rotto.db"
    broken.write_bytes(b"questo non e' un database sqlite" * 50)
    with pytest.raises(sqlite3.Error):
        backup_database(broken, folder, today=date(2026, 11, 5))
    assert list(folder.iterdir()) == []


def test_rotation_keeps_only_the_most_recent_backups(tmp_path: Path) -> None:
    for day in range(1, 8):
        (tmp_path / f"doughlab-2026-11-0{day}.db").write_bytes(b"x")
    (tmp_path / "altro.txt").write_text("resta")

    removed = rotate_backups(tmp_path, keep=3)

    assert [p.name for p in removed] == [f"doughlab-2026-11-0{d}.db" for d in (1, 2, 3, 4)]
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "altro.txt", "doughlab-2026-11-05.db", "doughlab-2026-11-06.db", "doughlab-2026-11-07.db"]
