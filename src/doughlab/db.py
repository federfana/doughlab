"""Setup del database asincrono (SQLAlchemy 2.0 + aiosqlite)."""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.schema import ColumnDefault

from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.db_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> set[tuple[str, str]]:
    """Crea le tabelle mancanti e aggiunge le colonne mancanti; restituisce le colonne aggiunte."""
    # Import locale per registrare i modelli prima del create_all.
    from . import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        return await conn.run_sync(_add_missing_columns)


def _sql_literal(value: object) -> str:
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def _add_missing_columns(connection: Connection) -> set[tuple[str, str]]:
    """`create_all` non tocca le tabelle esistenti: qui si aggiungono solo le colonne nuove."""
    inspector = inspect(connection)
    existing = set(inspector.get_table_names())
    added: set[tuple[str, str]] = set()
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            continue
        present = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            ddl = (
                f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" '
                f"{column.type.compile(dialect=connection.dialect)}"
            )
            if not column.nullable:
                default = column.default
                if not isinstance(default, ColumnDefault) or not default.is_scalar:
                    raise RuntimeError(
                        f"{table.name}.{column.name}: una colonna NOT NULL nuova ha bisogno di un "
                        "valore predefinito semplice per essere aggiunta a una tabella esistente"
                    )
                ddl += f" NOT NULL DEFAULT {_sql_literal(default.arg)}"
            connection.execute(text(ddl))
            added.add((table.name, column.name))
    return added
