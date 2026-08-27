"""Channel linking helpers (Telegram tokens, status)."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from marketplace.models import TelegramLinkToken, User


def _token_ttl_minutes() -> int:
    env = os.environ.get("AK_CHANNELS__TELEGRAM_LINK_TTL_MINUTES", "").strip()
    if env.isdigit():
        return max(5, int(env))
    return 15


def create_telegram_link_token(db: Session, user: User) -> tuple[str, str]:
    """Create single-use token; returns (raw_token, deep_link_url)."""
    raw = secrets.token_urlsafe(24)
    expires = datetime.now(timezone.utc) + timedelta(minutes=_token_ttl_minutes())
    row = TelegramLinkToken(user_id=user.id, token=raw, expires_at=expires)
    db.add(row)
    db.commit()
    bot = _telegram_bot_username()
    url = f"https://t.me/{bot}?start={raw}" if bot else f"/start {raw}"
    return raw, url


def consume_telegram_link_token(raw_token: str, chat_id: int) -> Optional[User]:
    db_factory = __import__("marketplace.database", fromlist=["SessionLocal"]).SessionLocal
    db = db_factory()
    try:
        now = datetime.now(timezone.utc)
        row = db.scalars(
            select(TelegramLinkToken).where(
                TelegramLinkToken.token == raw_token,
                TelegramLinkToken.used_at.is_(None),
            )
        ).first()
        if row is None or row.expires_at < now:
            return None
        user = db.get(User, row.user_id)
        if user is None or user.role != "farmer" or user.subscription_status != "active":
            return None
        claimant = db.scalars(select(User).where(User.telegram_chat_id == chat_id)).first()
        if claimant is not None and claimant.id != user.id:
            return None
        if user.telegram_chat_id is not None and user.telegram_chat_id != chat_id:
            return None
        user.telegram_chat_id = chat_id
        row.used_at = now
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def unlink_telegram(db: Session, user: User) -> None:
    user.telegram_chat_id = None
    db.commit()


def _telegram_bot_username() -> str:
    env = os.environ.get("AK_CHANNELS__TELEGRAM_BOT_USERNAME", "").strip()
    if env:
        return env.lstrip("@")
    try:
        import yaml

        with open("config.yaml", "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        cfg = (data.get("channels") or {}).get("telegram_bot_username")
        if isinstance(cfg, str) and cfg.strip():
            return cfg.strip().lstrip("@")
    except Exception:
        pass
    return "agripilot_bot"


def public_channel_config() -> dict:
    wa_display = os.environ.get("AK_CHANNELS__WHATSAPP_DISPLAY_NUMBER", "").strip()
    wa_me = os.environ.get("AK_CHANNELS__WHATSAPP_WA_ME", "").strip()
    bot = _telegram_bot_username()
    if not wa_display or not wa_me:
        try:
            import yaml

            with open("config.yaml", "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            ch = data.get("channels") or {}
            wa_display = wa_display or str(ch.get("whatsapp_display_number") or "")
            wa_me = wa_me or str(ch.get("whatsapp_wa_me") or "")
        except Exception:
            pass
    return {
        "whatsapp_display_number": wa_display or None,
        "whatsapp_wa_me": wa_me or None,
        "telegram_bot_username": bot or None,
        "telegram_deep_link_base": f"https://t.me/{bot}" if bot else None,
    }
