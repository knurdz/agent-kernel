"""Phase 15.1: DB models. Phase 18 adds the pending-duplicate partial index."""

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import marketplace.models  # noqa: F401  ensure tables registered
from marketplace.database import Base
from marketplace.models import ConnectionRequest, Listing, User


def test_init_creates_tables():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    # can insert a user
    u = User(
        phone_number="+94770000101",
        role="farmer",
        password_hash="hash",
        name="Test",
        subscription_status="active",
    )
    db.add(u)
    db.commit()
    assert u.id is not None
    db.close()


def test_duplicate_phone_raises():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    u1 = User(
        phone_number="+94770000102",
        role="farmer",
        password_hash="hash",
        name="A",
        subscription_status="active",
    )
    db.add(u1)
    db.commit()
    u2 = User(
        phone_number="+94770000102",
        role="buyer",
        password_hash="hash",
        name="B",
        subscription_status="active",
    )
    db.add(u2)
    try:
        db.commit()
        assert False, "expected IntegrityError"
    except IntegrityError:
        db.rollback()
    db.close()


def test_crop_lowercasing_via_service():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import marketplace.models  # noqa: F401
    from marketplace.database import Base
    from marketplace.models import User
    from marketplace.service import create_listing

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    farmer = User(
        phone_number="+94770000103",
        role="farmer",
        password_hash="hash",
        name="Farmer",
        subscription_status="active",
    )
    db.add(farmer)
    db.commit()
    listing = create_listing(db, farmer_id=farmer.id, crop="Tomato", quantity_kg=10)
    assert listing.crop == "tomato"
    assert listing.status == "active"
    db.close()


def test_quantity_validation():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import marketplace.models  # noqa: F401
    from marketplace.database import Base
    from marketplace.models import User
    from marketplace.service import create_listing

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    farmer = User(
        phone_number="+94770000104",
        role="farmer",
        password_hash="hash",
        name="Farmer2",
        subscription_status="active",
    )
    db.add(farmer)
    db.commit()
    try:
        create_listing(db, farmer_id=farmer.id, crop="rice", quantity_kg=0)
        assert False, "should raise"
    except ValueError as exc:
        assert "quantity_kg" in str(exc)
    try:
        create_listing(db, farmer_id=farmer.id, crop="rice", quantity_kg=5, price_per_kg=-1)
        assert False
    except ValueError:
        pass
    db.close()


# ---------- Phase 18: pending-duplicate partial unique index ----------

PENDING_IDX = "ux_connection_requests_pending"


def test_pending_unique_index_declared_for_both_dialects():
    table = ConnectionRequest.__table__
    idx = {i.name: i for i in table.indexes}.get(PENDING_IDX)
    assert idx is not None, f"{PENDING_IDX} missing from ConnectionRequest metadata"
    assert idx.unique
    assert idx.dialect_options["sqlite"]["where"] is not None
    assert idx.dialect_options["postgresql"]["where"] is not None


def _seed_farmer_buyer_listing(db):
    farmer = User(
        phone_number="+94770000110", role="farmer", password_hash="hash", name="F", subscription_status="active"
    )
    buyer = User(
        phone_number="+94770000111", role="buyer", password_hash="hash", name="B", subscription_status="active"
    )
    db.add_all([farmer, buyer])
    db.flush()
    listing = Listing(farmer_id=farmer.id, crop="rice", quantity_kg=5.0, status="active")
    db.add(listing)
    db.flush()
    return listing, buyer


def test_partial_index_blocks_second_pending_row():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    try:
        listing, buyer = _seed_farmer_buyer_listing(db)
        db.add(ConnectionRequest(listing_id=listing.id, buyer_id=buyer.id, status="pending"))
        db.commit()

        # Second pending row for the same (listing_id, buyer_id) violates the partial index.
        db.add(ConnectionRequest(listing_id=listing.id, buyer_id=buyer.id, status="pending"))
        try:
            db.commit()
            assert False, "expected IntegrityError from partial unique index"
        except IntegrityError:
            db.rollback()

        # A non-pending row never conflicts.
        db.add(ConnectionRequest(listing_id=listing.id, buyer_id=buyer.id, status="declined"))
        db.commit()
    finally:
        db.close()
        engine.dispose()


def test_partial_index_allows_new_pending_after_terminal():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    try:
        listing, buyer = _seed_farmer_buyer_listing(db)
        first = ConnectionRequest(listing_id=listing.id, buyer_id=buyer.id, status="accepted")
        db.add(first)
        db.commit()

        second = ConnectionRequest(listing_id=listing.id, buyer_id=buyer.id, status="pending")
        db.add(second)
        db.commit()  # must not raise
        pendings = db.scalars(
            select(ConnectionRequest).where(
                ConnectionRequest.listing_id == listing.id,
                ConnectionRequest.buyer_id == buyer.id,
                ConnectionRequest.status == "pending",
            )
        ).all()
        assert len(pendings) == 1
    finally:
        db.close()
        engine.dispose()
