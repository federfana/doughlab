"""Modelli SQLAlchemy di DoughLab."""
from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as date_type
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    style: Mapped[str] = mapped_column(String(40), default="napoletana")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    versions: Mapped[list[RecipeVersion]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", order_by="RecipeVersion.id.desc()"
    )


class RecipeVersion(Base):
    """Ogni modifica alla ricetta è una nuova versione: ricettario versionato."""

    __tablename__ = "recipe_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(default=1)
    message: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # payload: fasi, ingredienti, parametri — JSON per flessibilità in MVP.
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    recipe: Mapped[Recipe] = relationship(back_populates="versions")


class DiaryEntry(Base):
    """Una voce del diario: una prova reale, con foto, note e (se c'è) il piano da cui nasce."""

    __tablename__ = "diary_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Identificativo stabile (uuid): rende ripetibile l'importazione dei backup.
    external_id: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    date: Mapped[date_type] = mapped_column(Date, index=True)
    pizza_type: Mapped[str] = mapped_column(String(60), default="")
    preferment: Mapped[str] = mapped_column(String(60), default="")
    oven: Mapped[str] = mapped_column(String(80), default="")
    flour: Mapped[str] = mapped_column(String(200), default="")
    flour_w: Mapped[float | None] = mapped_column(Float, default=None)
    protein: Mapped[float | None] = mapped_column(Float, default=None)
    hydration: Mapped[float | None] = mapped_column(Float, default=None)
    cold_hours: Mapped[float | None] = mapped_column(Float, default=None)
    room_hours: Mapped[float | None] = mapped_column(Float, default=None)
    dough_ball_weight: Mapped[float | None] = mapped_column(Float, default=None)
    dough_ball_count: Mapped[int | None] = mapped_column(Integer, default=None)
    dough_temp: Mapped[float | None] = mapped_column(Float, default=None)
    bake_temp: Mapped[float | None] = mapped_column(Float, default=None)
    bake_time: Mapped[str] = mapped_column(String(40), default="")
    bake_setup: Mapped[str] = mapped_column(String(200), default="")
    rating: Mapped[float | None] = mapped_column(Float, default=None)
    ingredients: Mapped[str] = mapped_column(Text, default="")
    process: Mapped[str] = mapped_column(Text, default="")
    bake: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    next_changes: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(String(200), default="")
    # Piano DoughLab da cui nasce la prova e orari reali, per confrontare con la stima.
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    # Chiavi di backup sconosciute, restituite tali e quali nell'export.
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    photos: Mapped[list[DiaryPhoto]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DiaryPhoto.id",
    )


class DiaryPhoto(Base):
    __tablename__ = "diary_photos"
    __table_args__ = (UniqueConstraint("entry_id", "slot"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("diary_entries.id", ondelete="CASCADE"))
    slot: Mapped[str] = mapped_column(String(10))
    mime: Mapped[str] = mapped_column(String(40))
    # Caricata solo quando serve (serve la foto o l'export), non a ogni elenco.
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    entry: Mapped[DiaryEntry] = relationship(back_populates="photos")
