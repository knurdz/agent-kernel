"""Database engine/session for AgriPilot marketplace (Phase 15).

Uses ``AK_MARKETPLACE__DATABASE_URL`` env var when set, otherwise
``config.yaml: marketplace.database_url`` (default ``sqlite:///./data/app.db``).
SQLite uses ``check_same_thread=False`` and a single file; Postgres uses
``pool_pre_ping=True``.
"""

from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

try:
    import yaml  # type: ignore

    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

DEFAULT_URL = "sqlite:///./data/app.db"


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
    connect_args: dict = {}
    if target.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        engine_ = create_engine(target, connect_args=connect_args, echo=False, future=True)
    else:
        engine_ = create_engine(target, pool_pre_ping=True, echo=False, future=True)
    return engine_


# Global engine/session for the app (lazy but module-level so imports work).
# Tests override via dependency injection or by creating their own engine.
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


def init_db(url: str | None = None) -> None:
    """Create all marketplace tables (idempotent)."""
    if url:
        eng = _build_engine(url)
        # Import models so Base metadata is populated.
        import marketplace.models  # noqa: F401

        Base.metadata.create_all(bind=eng)
        eng.dispose()
    else:
        import marketplace.models  # noqa: F401

        Base.metadata.create_all(bind=engine)
