"""FCM device registration and notification preferences."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from marketplace.auth import get_current_user
from marketplace.database import get_db
from marketplace.models import NotificationPreference, User, UserDevice
from marketplace.schemas import (
    DeviceRegisterRequest,
    DeviceResponse,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
)

router = APIRouter(prefix="/api/devices", tags=["devices"])


def _get_or_create_prefs(db: Session, user_id: int) -> NotificationPreference:
    prefs = db.get(NotificationPreference, user_id)
    if prefs is None:
        prefs = NotificationPreference(user_id=user_id)
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
    return prefs


@router.post("/register", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
def register_device(
    payload: DeviceRegisterRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = db.scalars(select(UserDevice).where(UserDevice.fcm_token == payload.fcm_token)).first()
    if existing:
        if existing.user_id != user.id:
            raise HTTPException(status_code=409, detail="token registered to another user")
        existing.active = True
        existing.platform = payload.platform
        db.commit()
        db.refresh(existing)
        return existing
    device = UserDevice(user_id=user.id, fcm_token=payload.fcm_token, platform=payload.platform, active=True)
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@router.delete("/unregister", status_code=status.HTTP_204_NO_CONTENT)
def unregister_device(
    fcm_token: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device = db.scalars(
        select(UserDevice).where(UserDevice.fcm_token == fcm_token, UserDevice.user_id == user.id)
    ).first()
    if device:
        device.active = False
        db.commit()
    return None


@router.get("/notification-preferences", response_model=NotificationPreferencesResponse)
def get_notification_preferences(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _get_or_create_prefs(db, user.id)


@router.patch("/notification-preferences", response_model=NotificationPreferencesResponse)
def update_notification_preferences(
    payload: NotificationPreferencesUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    prefs = _get_or_create_prefs(db, user.id)
    if payload.push_enabled is not None:
        prefs.push_enabled = payload.push_enabled
    if payload.whatsapp_enabled is not None:
        prefs.whatsapp_enabled = payload.whatsapp_enabled
    if payload.connection_updates is not None:
        prefs.connection_updates = payload.connection_updates
    db.commit()
    db.refresh(prefs)
    return prefs
