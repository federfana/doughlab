"""Modelli SQLAlchemy di DoughLab."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    style: Mapped[str] = mapped_column(String(40), default="napoletana")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # payload: fasi, ingredienti, parametri — JSON per flessibilità in MVP.
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    recipe: Mapped[Recipe] = relationship(back_populates="versions")


class Bake(Base):
    """Una prova reale: snapshot del piano più l'esito osservato."""

    __tablename__ = "bakes"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipes.id", ondelete="SET NULL"))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notes: Mapped[str] = mapped_column(Text, default="")
    rating: Mapped[int | None] = mapped_column(default=None)
    # [{"kind": "plan", "snapshot": ...}, {"kind": "observation", "actual_ready_at": ..., "baking": ...}]
    log: Mapped[list[Any]] = mapped_column(JSON, default=list)
