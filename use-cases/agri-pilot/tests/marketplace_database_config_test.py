"""Phase 18.1: database module is Postgres-only at runtime.

Tests keep per-test in-memory SQLite engines; these checks pin the runtime
defaults, URL precedence, and the Alembic-only schema authority.
"""

import marketplace.database as dbmod
from marketplace.database import DEFAULT_URL, get_database_url

ENV_VAR = "AK_MARKETPLACE__DATABASE_URL"


def test_default_url_is_postgres_psycopg3():
    assert DEFAULT_URL.startswith("postgresql+psycopg://")


def test_default_resolution_is_postgres(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert get_database_url().startswith("postgresql+psycopg://")


def test_env_var_wins_over_config_and_default(monkeypatch):
    sentinel = "postgresql+psycopg://u:p@dbhost:5432/dbx"
    monkeypatch.setenv(ENV_VAR, sentinel)
    assert get_database_url() == sentinel


def test_engine_uses_pre_ping():
    # Global engine must be built lazily (no connection at import) with pre-ping.
    assert dbmod.engine.pool._pre_ping


def test_init_db_replaced_by_run_migrations():
    import marketplace as mpkg

    assert not hasattr(dbmod, "init_db"), "init_db/create_all must not remain a schema path"
    assert not hasattr(dbmod, "_ensure_farmer_contact_column"), "SQLite PRAGMA patch-up must be gone"
    assert callable(dbmod.run_migrations)
    assert "init_db" not in mpkg.__all__
    assert "run_migrations" in mpkg.__all__


def test_sqlite_branch_removed_from_engine_builder():
    # _build_engine should no longer special-case sqlite; connect_args stays empty.
    eng = dbmod._build_engine("sqlite:///:memory:")
    try:
        assert str(eng.url) == "sqlite:///:memory:"
        assert eng.pool._pre_ping
    finally:
        eng.dispose()
