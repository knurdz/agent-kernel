"""Best-effort WhatsApp notification for new connection requests (Phase 16.3)."""

from __future__ import annotations

import logging
import os

log = logging.getLogger("agripilot.marketplace.notifications")


def notify_farmer_of_request(farmer_id: int, listing_id: int, connection_id: int) -> None:
    """Notify farmer of a new buyer interest via WhatsApp (best-effort, never raises)."""
    try:
        phone_id = os.environ.get("AK_WHATSAPP__PHONE_NUMBER_ID")
        token = os.environ.get("AK_WHATSAPP__ACCESS_TOKEN")
        if not phone_id or not token:
            log.info(
                "notify stub: farmer %s listing %s connection %s (no WhatsApp creds)",
                farmer_id,
                listing_id,
                connection_id,
            )
            return

        # Lazy import to avoid hard dependency at module import time
        from sqlalchemy.orm import Session  # noqa: F401

        from marketplace.database import SessionLocal
        from marketplace.models import Listing, User

        db = SessionLocal()
        try:
            farmer = db.get(User, farmer_id)
            listing = db.get(Listing, listing_id)
            if not farmer or not listing:
                return
            # Only if farmer subscription active (even though notify is best-effort)
            if (
                farmer.subscription_status != "active"
                and os.environ.get("AK_MARKETPLACE__SKIP_SUBSCRIPTION_CHECK") != "1"
            ):
                log.info("notify skipped: farmer %s subscription %s", farmer_id, farmer.subscription_status)
                return

            crop = listing.crop
            qty = listing.quantity_kg
            body = f"New buyer interest on your {crop} listing ({qty}kg). Open AgriPilot to respond."

            # Use httpx if available, else try requests
            url = f"https://graph.facebook.com/v20.0/{phone_id}/messages"
            headers = {"Authorization": f"Bearer {token}"}
            payload = {
                "messaging_product": "whatsapp",
                "to": farmer.phone_number,
                "type": "text",
                "text": {"body": body},
            }
            try:
                import httpx

                resp = httpx.post(url, headers=headers, json=payload, timeout=5)
                log.info("notify sent farmer %s status %s", farmer_id, getattr(resp, "status_code", "?"))
            except ImportError:
                import requests  # type: ignore

                resp = requests.post(url, headers=headers, json=payload, timeout=5)
                log.info("notify sent farmer %s status %s", farmer_id, getattr(resp, "status_code", "?"))
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("notify_farmer_of_request failed: %s", exc, exc_info=False)
