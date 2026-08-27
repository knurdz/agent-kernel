"""Phase 18.2: Alembic migrations (offline-safe, runs on tmp SQLite file DBs).

The real-Postgres counterpart lives in ``marketplace_postgres_smoke_test.py``
(skipped unless Postgres is reachable).
"""

import pathlib

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

ROOT = pathlib.Path(__file__).resolve().parents[1]

EXPECTED_TABLES = {"users", "farmer_profiles", "buyer_profiles", "listings", "connection_requests"}

# Reused phone numbers per test DB — each test gets its own fresh file.
FARMER_PHONE = "+94770000301"
BUYER_PHONE = "+94770000302"


def _cfg(db_url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _upgrade(url: str) -> None:
    command.upgrade(_cfg(url), "head")


def _downgrade(url: str, rev: str) -> None:
    command.downgrade(_cfg(url), rev)


def _table_columns(engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


def _user_tables(engine) -> set[str]:
    tables = set(inspect(engine).get_table_names())
    tables.discard("alembic_version")
    return tables


def test_upgrade_head_creates_marketplace_schema(tmp_path):
    url = f"sqlite:///{tmp_path/'mig.db'}"
    _upgrade(url)

    from sqlalchemy import create_engine

    engine = create_engine(url)
    assert EXPECTED_TABLES <= _user_tables(engine)
    # The Phase 17 hot-patched column must be part of the baseline revision.
    assert "contact_phone" in _table_columns(engine, "farmer_profiles")
    # Telegram linking column (contact-share flow) added in b4e8f1a2c7d9.
    assert "telegram_chat_id" in _table_columns(engine, "users")
    engine.dispose()


def test_migrated_schema_matches_metadata(tmp_path):
    """Drift guard: Alembic-created schema and Base.metadata agree."""
    mig_url = f"sqlite:///{tmp_path/'mig.db'}"
    meta_url = f"sqlite:///{tmp_path/'meta.db'}"

    _upgrade(mig_url)

    from sqlalchemy import create_engine

    import marketplace.models  # noqa: F401
    from marketplace.database import Base

    meta_engine = create_engine(meta_url)
    Base.metadata.create_all(bind=meta_engine)

    assert _user_tables(create_engine(mig_url)) == _user_tables(meta_engine)
    for table in sorted(EXPECTED_TABLES):
        assert _table_columns(create_engine(mig_url), table) == _table_columns(meta_engine, table)
        meta_engine.dispose()


def test_downgrade_then_upgrade_roundtrip(tmp_path):
    url = f"sqlite:///{tmp_path/'mig.db'}"
    _upgrade(url)
    _downgrade(url, "base")

    from sqlalchemy import create_engine

    engine = create_engine(url)
    assert _user_tables(engine).isdisjoint(EXPECTED_TABLES)
    engine.dispose()

    _upgrade(url)  # re-applies cleanly
    engine = create_engine(url)
    assert EXPECTED_TABLES <= _user_tables(engine)
    engine.dispose()


def test_service_crud_on_migrated_db(tmp_path):
    """Full write path works against the migrated schema (not create_all)."""
    url = f"sqlite:///{tmp_path/'mig.db'}"
    _upgrade(url)

    from sqlalchemy import create_engine

    from marketplace import service
    from marketplace.auth import hash_password

    engine = create_engine(url)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    try:
        farmer = service.create_user_with_profile(
            db,
            role="farmer",
            phone_number=FARMER_PHONE,
            password_hash=hash_password("secret123"),
            name="Amal",
            district="Kandy",
            contact_phone="+94770000399",
        )
        buyer = service.create_user_with_profile(
            db,
            role="buyer",
            phone_number=BUYER_PHONE,
            password_hash=hash_password("secret123"),
            name="Buyer",
            district="Galle",
        )
        assert farmer.farmer_profile.contact_phone == "+94770000399"

        listing = service.create_listing(db, farmer_id=farmer.id, crop="Tomato", quantity_kg=12.5, price_per_kg=80.0)
        assert service.list_own_listings(db, farmer.id)[0].id == listing.id

        conn = service.create_connection_request(db, buyer_id=buyer.id, listing_id=listing.id)
        assert conn.status == "pending"

        # App-level pending-uniqueness guard still holds on the migrated schema.
        with pytest.raises(ValueError, match="already requested"):
            service.create_connection_request(db, buyer_id=buyer.id, listing_id=listing.id)

        accepted = service.update_connection_status(
            db, farmer_id=farmer.id, connection_id=conn.id, new_status="accepted"
        )
        assert accepted.status == "accepted"

        # Once accepted (not pending anymore), a new pending request is allowed.
        again = service.create_connection_request(db, buyer_id=buyer.id, listing_id=listing.id)
        assert again.status == "pending"
    finally:
        db.close()
        engine.dispose()
