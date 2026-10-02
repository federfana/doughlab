"""Configurazione globale (letta da env + .env)."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DOUGHLAB_", extra="ignore")

    app_name: str = "DoughLab"
    debug: bool = True

    db_url: str = Field(default=f"sqlite+aiosqlite:///{DATA_DIR / 'doughlab.db'}")

    default_ambient_c: float = 22.0
    default_fridge_c: float = 4.0


settings = Settings()
