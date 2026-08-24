"""Auth router: signup / login / me (App.md:46-48)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from marketplace.auth import create_access_token, get_current_user, hash_password, normalize_phone, verify_password
from marketplace.database import get_db
from marketplace.models import BuyerProfile, FarmerProfile, User
from marketplace.schemas import LoginRequest, MeResponse, ProfileOut, SignupRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    phone = normalize_phone(payload.phone_number)
    existing = db.scalars(select(User).where(User.phone_number == phone)).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="phone already registered")

    if payload.role == "admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="use seed script for admin")

    pwd_hash = hash_password(payload.password)

    # New farmers/buyers default to active so local dev isn't dead-ended (Phase 15.3 note).
    user = User(
        phone_number=phone,
        role=payload.role,
        password_hash=pwd_hash,
        name=payload.name,
        subscription_status="active",
    )
    db.add(user)
    db.flush()
    if payload.role == "farmer":
        db.add(
            FarmerProfile(
                user_id=user.id,
                location=payload.location,
                district=payload.district,
                preferred_language=payload.preferred_language,
            )
        )
    else:
        db.add(
            BuyerProfile(
                user_id=user.id,
                business_name=payload.business_name,
                location=payload.location,
                district=payload.district,
            )
        )
    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "phone_number": user.phone_number,
        "role": user.role,
        "subscription_status": user.subscription_status,
    }


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    phone = normalize_phone(payload.phone_number)
    user = db.scalars(select(User).where(User.phone_number == phone)).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    token = create_access_token(user.id, user.role)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Load profile eagerly if needed; relationships may be None.
    profile = None
    if user.role == "farmer" and user.farmer_profile:
        p = user.farmer_profile
        profile = ProfileOut(location=p.location, district=p.district, preferred_language=p.preferred_language)
    elif user.role == "buyer" and user.buyer_profile:
        p = user.buyer_profile
        profile = ProfileOut(business_name=p.business_name, location=p.location, district=p.district)
    return MeResponse(
        id=user.id,
        phone_number=user.phone_number,
        role=user.role,
        subscription_status=user.subscription_status,
        name=user.name,
        created_at=user.created_at,
        profile=profile,
    )
