"""Seed an admin user (optional, for Phase 15)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from marketplace.auth import hash_password, normalize_phone
from marketplace.database import SessionLocal, init_db
from marketplace.models import User

if __name__ == "__main__":
    phone = os.environ.get("AK_MARKETPLACE__ADMIN_PHONE")
    pwd = os.environ.get("AK_MARKETPLACE__ADMIN_PASSWORD")
    name = os.environ.get("AK_MARKETPLACE__ADMIN_NAME", "Admin")
    if not phone or not pwd:
        print("Set AK_MARKETPLACE__ADMIN_PHONE and AK_MARKETPLACE__ADMIN_PASSWORD to seed admin")
        raise SystemExit(0)
    init_db()
    db = SessionLocal()
    try:
        norm = normalize_phone(phone)
        existing = db.scalars(select(User).where(User.phone_number == norm)).first()
        if existing:
            print(f"exists: {existing.phone_number} role={existing.role}")
            raise SystemExit(0)
        user = User(
            phone_number=norm,
            role="admin",
            password_hash=hash_password(pwd),
            name=name,
            subscription_status="active",
        )
        db.add(user)
        db.commit()
        print(f"created admin {norm}")
    finally:
        db.close()
