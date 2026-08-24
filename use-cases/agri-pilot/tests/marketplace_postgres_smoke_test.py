"""Phase 18.5: smoke chain on real Postgres.

Skipped unless ``AK_MARKETPLACE__DATABASE_URL`` (default
``postgresql+psycopg://agripilot:agripilot@localhost:5432/agripilot``) is
reachable. Verifies no SQLite-isms survive the cutover: migrations apply and
the full marketplace write path works on Postgres.
"""

import os

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

PG_URL = os.environ.get(
    "AK_MARKETPLACE__DATABASE_URL",
    "postgresql+psycopg://agripilot:agripilot@localhost:5432/agripilot",
)

FARMER_PHONE = "+94770000401"
BUYER_PHONE = "+94770000402"


def _postgres_reachable() -> bool:
    try:
        engine = create_engine(PG_URL, connect_args={"connect_timeout": 2})
        with engine.connect():
            return True
    except Exception:
        return False


def _cfg():
    import pathlib

    from alembic.config import Config

    root = pathlib.Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", PG_URL)
    return cfg


@pytest.fixture()
def migrated_postgres():
    assert _postgres_reachable(), "Postgres became unreachable between probe and fixture"
    command.upgrade(_cfg(), "head")
    yield
    command.downgrade(_cfg(), "base")


@pytest.mark.skipif(not _postgres_reachable(), reason="no Postgres reachable at AK_MARKETPLACE__DATABASE_URL")
def test_pending_unique_partial_index_exists(migrated_postgres):
    engine = create_engine(PG_URL)
    try:
        indexes = inspect(engine).get_indexes("connection_requests")
        names = {i["name"] for i in indexes}
        assert "ux_connection_requests_pending" in names
        assert next(i for i in indexes if i["name"] == "ux_connection_requests_pending")["unique"]
    finally:
        engine.dispose()


@pytest.mark.skipif(not _postgres_reachable(), reason="no Postgres reachable at AK_MARKETPLACE__DATABASE_URL")
def test_full_marketplace_chain_on_postgres(migrated_postgres):
    from marketplace import service
    from marketplace.auth import hash_password

    engine = create_engine(PG_URL)
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
            contact_phone="+94770000499",
        )
        buyer = service.create_user_with_profile(
            db,
            role="buyer",
            phone_number=BUYER_PHONE,
            password_hash=hash_password("secret123"),
            name="Buyer",
            district="Kandy",
        )

        listing = service.create_listing(db, farmer_id=farmer.id, crop="Tomato", quantity_kg=40.0, price_per_kg=120.0)
        matches = service.match_listings(db, district="kandy", crop="tomato", limit=10)
        assert any(m["listing"].id == listing.id for m in matches)

        conn = service.create_connection_request(db, buyer_id=buyer.id, listing_id=listing.id)
        accepted = service.update_connection_status(
            db, farmer_id=farmer.id, connection_id=conn.id, new_status="accepted"
        )
        _, _, contact = service.get_connection_contact(
            db, connection_id=conn.id, requester_id=buyer.id, requester_role="buyer"
        )
        assert accepted.status == "accepted"
        assert contact == "+94770000499"  # farmer contact_phone reveal
    finally:
        db.close()
        engine.dispose()


@pytest.mark.skipif(not _postgres_reachable(), reason="no Postgres reachable at AK_MARKETPLACE__DATABASE_URL")
def test_duplicate_pending_blocked_by_partial_index(migrated_postgres):
    """The DB-level partial index (not just the service guard) rejects a second pending row."""
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from marketplace.models import ConnectionRequest, Listing, User

    engine = create_engine(PG_URL)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    try:
        farmer = User(
            phone_number=FARMER_PHONE, role="farmer", password_hash="h", name="F", subscription_status="active"
        )
        buyer = User(phone_number=BUYER_PHONE, role="buyer", password_hash="h", name="B", subscription_status="active")
        db.add_all([farmer, buyer])
        db.flush()
        listing = Listing(farmer_id=farmer.id, crop="rice", quantity_kg=5.0, status="active")
        db.add(listing)
        db.flush()
        db.add(ConnectionRequest(listing_id=listing.id, buyer_id=buyer.id, status="pending"))
        db.commit()

        db.add(ConnectionRequest(listing_id=listing.id, buyer_id=buyer.id, status="pending"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        # accepted + new pending coexist
        first = db.scalars(select(ConnectionRequest).where(ConnectionRequest.buyer_id == buyer.id)).first()
        first.status = "accepted"
        db.commit()
        db.add(ConnectionRequest(listing_id=listing.id, buyer_id=buyer.id, status="pending"))
        db.commit()  # must not raise
    finally:
        db.close()
        engine.dispose()
