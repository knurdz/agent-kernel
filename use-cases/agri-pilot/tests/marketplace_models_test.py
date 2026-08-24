"""Phase 15.1: DB models."""

from sqlalchemy import create_engine
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
