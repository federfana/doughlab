"""Copia giornaliera del database SQLite (diario, foto, ricette, farine) con rotazione."""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import date
from pathlib import Path

from ..config import DATA_DIR

BACKUP_DIR = DATA_DIR / "backups"
KEEP_BACKUPS = 14
PREFIX = "doughlab-"
CHECK_EVERY_SECONDS = 6 * 3600


def sqlite_path(db_url: str) -> Path | None:
    """Percorso del file se l'URL è SQLite su disco, altrimenti None (es. database in memoria)."""
    if not db_url.startswith("sqlite"):
        return None
    path = db_url.split(":///", 1)[-1].split("?", 1)[0]
    return Path(path) if path and path != ":memory:" else None


def backup_database(source: Path, backup_dir: Path = BACKUP_DIR, today: date | None = None,
                    keep: int = KEEP_BACKUPS) -> Path | None:
    """Crea la copia del giorno se manca; restituisce il file creato (None se già presente o senza database).

    Usa l'API di backup di SQLite: la copia è coerente anche mentre l'app scrive.
    """
    if not source.exists():
        return None
    target = backup_dir / f"{PREFIX}{(today or date.today()).isoformat()}.db"
    if target.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".db.partial")
    partial.unlink(missing_ok=True)
    origin = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        copy = sqlite3.connect(partial)
        try:
            origin.backup(copy)
        finally:
            copy.close()
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    finally:
        origin.close()
    partial.replace(target)
    rotate_backups(backup_dir, keep)
    return target


def rotate_backups(backup_dir: Path, keep: int) -> list[Path]:
    """Elimina le copie più vecchie, tenendo le `keep` più recenti; restituisce quelle eliminate."""
    files = sorted(backup_dir.glob(f"{PREFIX}????-??-??.db"))
    old = files[:-keep] if keep > 0 else files
    for path in old:
        path.unlink(missing_ok=True)
    return old


async def backup_loop(source: Path) -> None:
    """Fa la copia all'avvio e poi controlla ogni poche ore (il server resta acceso per giorni)."""
    while True:
        try:
            await asyncio.to_thread(backup_database, source)
        except (OSError, sqlite3.Error) as error:
            print(f"Backup del database non riuscito: {error}")
        await asyncio.sleep(CHECK_EVERY_SECONDS)
