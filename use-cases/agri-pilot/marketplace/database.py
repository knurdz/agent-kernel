"""Database engine/session for AgriPilot marketplace (Phase 15; Postgres-only since Phase 18).

Uses ``AK_MARKETPLACE__DATABASE_URL`` env var when set, otherwise
``config.yaml: marketplace.database_url``, otherwise ``DEFAULT_URL``.
Postgres is the only runtime backend (driver: psycopg 3). Schema changes go
through Alembic (``migrations/``); call :func:`run_migrations` at startup or
run ``uv run python -m alembic upgrade head`` manually. Tests use their own
in-memory SQLite engines plus ``Base.metadata.create_all``.
"""

from __future__ import annotations

import os
import pathlib
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

try:
    import yaml  # type: ignore

    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

DEFAULT_URL = "postgresql+psycopg://agripilot:agripilot@localhost:5432/agripilot"

_ALEMBIC_INI = pathlib.Path(__file__).resolve().parents[1] / "alembic.ini"


def _read_config_url() -> str | None:
    if not _HAS_YAML:
        return None
    try:
        with open("config.yaml", "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        mp = data.get("marketplace") or {}
        url = mp.get("database_url")
        if isinstance(url, str) and url.strip():
            return url.strip()
    except FileNotFoundError:
        return None
    except Exception:
        return None
    return None


def get_database_url() -> str:
    env_url = os.environ.get("AK_MARKETPLACE__DATABASE_URL")
    if env_url and env_url.strip():
        return env_url.strip()
    cfg_url = _read_config_url()
    if cfg_url:
        return cfg_url
    return DEFAULT_URL


def _build_engine(url: str | None = None):
    target = url or get_database_url()
    return create_engine(target, pool_pre_ping=True, echo=False, future=True)


# Global engine/session for the app. Engines connect lazily, so importing this
# module never opens a connection (tests inject their own engines).
engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations(url: str | None = None) -> None:
    """Apply pending Alembic migrations to the configured (or given) database.

    The single schema-authority path used at app startup; equivalent to
    ``uv run python -m alembic upgrade head`` with ``AK_MARKETPLACE__DATABASE_URL`` set.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_INI))
    if url:
        cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
