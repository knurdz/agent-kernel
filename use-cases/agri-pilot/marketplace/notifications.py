"""Notification dispatcher: WhatsApp + FCM (best-effort, never raises)."""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

log = logging.getLogger("agripilot.marketplace.notifications")


def _fcm_enabled() -> bool:
    if os.environ.get("AK_NOTIFICATIONS__FCM_ENABLED", "").lower() in {"1", "true", "yes"}:
        return True
    try:
        import yaml

        with open("config.yaml", "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return bool((data.get("notifications") or {}).get("fcm_enabled"))
    except Exception:
        return False


def _send_whatsapp_text(phone: str, body: str) -> None:
    phone_id = os.environ.get("AK_WHATSAPP__PHONE_NUMBER_ID")
    token = os.environ.get("AK_WHATSAPP__ACCESS_TOKEN")
    if not phone_id or not token:
        log.info("whatsapp notify stub: to=%s", phone)
        return
    url = f"https://graph.facebook.com/v20.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": body},
    }
    try:
        import httpx

        resp = httpx.post(url, headers=headers, json=payload, timeout=5)
        log.info("whatsapp notify to %s status %s", phone, getattr(resp, "status_code", "?"))
    except Exception as exc:  # noqa: BLE001
        log.warning("whatsapp notify failed: %s", exc)


def _send_fcm(user_id: int, title: str, body: str, data: Optional[dict] = None) -> None:
    if not _fcm_enabled():
        log.debug("fcm disabled; skip user=%s title=%s", user_id, title)
        return
    creds_path = os.environ.get("AK_NOTIFICATIONS__FIREBASE_CREDENTIALS_PATH", "").strip()
    if not creds_path:
        try:
            import yaml

            with open("config.yaml", "r", encoding="utf-8") as fh:
                cfg = yaml.safe_load(fh) or {}
            creds_path = str((cfg.get("notifications") or {}).get("firebase_credentials_path") or "")
        except Exception:
            creds_path = ""
    if not creds_path or not os.path.isfile(creds_path):
        log.info("fcm stub user=%s title=%s", user_id, title)
        return
    try:
        from sqlalchemy import select

        from marketplace.database import SessionLocal
        from marketplace.models import NotificationPreference, UserDevice

        db = SessionLocal()
        try:
            prefs = db.get(NotificationPreference, user_id)
            if prefs is not None and not prefs.push_enabled:
                return
            tokens = db.scalars(
                select(UserDevice.fcm_token).where(UserDevice.user_id == user_id, UserDevice.active.is_(True))
            ).all()
        finally:
            db.close()
        if not tokens:
            return
        # Lazy import firebase_admin — optional at runtime
        import firebase_admin
        from firebase_admin import credentials, messaging

        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(creds_path))
        for tok in tokens:
            msg = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data={k: str(v) for k, v in (data or {}).items()},
                token=tok,
            )
            messaging.send(msg)
            log.info("fcm sent user=%s token=%s...", user_id, tok[:8])
    except Exception as exc:  # noqa: BLE001
        log.warning("fcm send failed user=%s: %s", user_id, exc)


def notify_farmer_of_request(farmer_id: int, listing_id: int, connection_id: int) -> None:
    """Notify farmer of new buyer interest (WhatsApp + FCM)."""
    try:
        from marketplace.database import SessionLocal
        from marketplace.models import Listing, NotificationPreference, User

        db = SessionLocal()
        try:
            farmer = db.get(User, farmer_id)
            listing = db.get(Listing, listing_id)
            if not farmer or not listing:
                return
            if farmer.subscription_status != "active" and os.environ.get("AK_MARKETPLACE__SKIP_SUBSCRIPTION_CHECK") != "1":
                return
            prefs = db.get(NotificationPreference, farmer_id)
            crop = listing.crop
            qty = listing.quantity_kg
            body = f"New buyer interest on your {crop} listing ({qty}kg). Open AgriPilot to respond."
            if prefs is None or prefs.whatsapp_enabled:
                _send_whatsapp_text(farmer.phone_number, body)
            if prefs is None or prefs.connection_updates:
                _send_fcm(
                    farmer_id,
                    "New buyer interest",
                    body,
                    {"type": "connection_request", "connection_id": str(connection_id), "listing_id": str(listing_id)},
                )
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("notify_farmer_of_request failed: %s", exc, exc_info=False)


def notify_buyer_connection_update(buyer_id: int, connection_id: int, status: str, crop: str) -> None:
    """Notify buyer when farmer accepts/declines/completes a connection."""
    try:
        title = "Connection update"
        body = f"Your request for {crop} was {status}."
        _send_fcm(
            buyer_id,
            title,
            body,
            {"type": "connection_update", "connection_id": str(connection_id), "status": status},
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("notify_buyer_connection_update failed: %s", exc, exc_info=False)
