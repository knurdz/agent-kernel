"""Auth router: signup / login / me (App.md:46-48)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from marketplace.auth import create_access_token, get_current_user, hash_password, normalize_phone, verify_password
from marketplace.channels import (
    create_telegram_link_token,
    unlink_telegram,
)
from marketplace.database import get_db
from marketplace.models import BuyerProfile, FarmerProfile, User
from marketplace.schemas import (
    ChannelsResponse,
    LoginRequest,
    MeResponse,
    ProfileOut,
    ProfileUpdate,
    SignupRequest,
    TelegramChannelStatus,
    TelegramLinkTokenResponse,
    TokenResponse,
    WhatsAppChannelStatus,
)

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

    # Farmer defaults to active, buyer to none (no subscription for buyers — Phases 16/17).
    # Contact phone only for farmers (optional, fallback to primary phone for buyer display).
    sub_status = "active" if payload.role == "farmer" else "none"
    contact_phone_norm = None
    if payload.role == "farmer" and payload.contact_phone_number:
        try:
            contact_phone_norm = normalize_phone(payload.contact_phone_number)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    user = User(
        phone_number=phone,
        role=payload.role,
        password_hash=pwd_hash,
        name=payload.name,
        subscription_status=sub_status,
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
                contact_phone=contact_phone_norm,
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
        profile = ProfileOut(
            location=p.location,
            district=p.district,
            preferred_language=p.preferred_language,
            contact_phone=p.contact_phone,
        )
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


@router.patch("/me", response_model=MeResponse)
def update_me(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.name is not None:
        user.name = payload.name
    if user.role == "farmer":
        if user.farmer_profile is None:
            db.add(FarmerProfile(user_id=user.id))
            db.flush()
        fp = user.farmer_profile
        if payload.location is not None:
            fp.location = payload.location
        if payload.district is not None:
            fp.district = payload.district
        if payload.preferred_language is not None:
            fp.preferred_language = payload.preferred_language
        if payload.contact_phone_number is not None:
            fp.contact_phone = normalize_phone(payload.contact_phone_number) if payload.contact_phone_number else None
    elif user.role == "buyer":
        if user.buyer_profile is None:
            db.add(BuyerProfile(user_id=user.id))
            db.flush()
        bp = user.buyer_profile
        if payload.business_name is not None:
            bp.business_name = payload.business_name
        if payload.location is not None:
            bp.location = payload.location
        if payload.district is not None:
            bp.district = payload.district
    db.commit()
    db.refresh(user)
    return me(user=user, db=db)


@router.get("/me/channels", response_model=ChannelsResponse)
def get_channels(user: User = Depends(get_current_user)):
    farmer_active = user.role == "farmer" and user.subscription_status == "active"
    return ChannelsResponse(
        telegram=TelegramChannelStatus(linked=user.telegram_chat_id is not None, eligible=farmer_active),
        whatsapp=WhatsAppChannelStatus(eligible=farmer_active, linked_by_phone=farmer_active),
    )


@router.post("/me/channels/telegram/link-token", response_model=TelegramLinkTokenResponse)
def telegram_link_token(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "farmer":
        raise HTTPException(status_code=403, detail="farmer role required")
    if user.subscription_status != "active":
        raise HTTPException(status_code=403, detail="farmer subscription required")
    _raw, url = create_telegram_link_token(db, user)
    import os

    ttl = int(os.environ.get("AK_CHANNELS__TELEGRAM_LINK_TTL_MINUTES", "15") or 15)
    return TelegramLinkTokenResponse(token=_raw, deep_link_url=url, expires_in_minutes=ttl)


@router.delete("/me/channels/telegram", status_code=status.HTTP_204_NO_CONTENT)
def unlink_telegram_channel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "farmer":
        raise HTTPException(status_code=403, detail="farmer role required")
    unlink_telegram(db, user)
    return None
