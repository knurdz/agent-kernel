"""Canonical session keys and marketplace identity seeding (mobile API)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from agentkernel.core.base import Session

    from marketplace.models import User

CANONICAL_PREFIX = "agri:user:"


def canonical_session_id(user_id: int) -> str:
    """Stable session key shared across mobile, WhatsApp, and Telegram."""
    return f"{CANONICAL_PREFIX}{user_id}"


def user_session_prefix(user_id: int) -> str:
    """Prefix for any session owned by a marketplace user (canonical or mobile thread)."""
    return f"{CANONICAL_PREFIX}{user_id}"


def is_user_owned_session(session_id: str | None, user_id: int) -> bool:
    """True when session_id belongs to the user (main channel thread or mobile sub-thread)."""
    if not session_id:
        return False
    sid = str(session_id)
    prefix = user_session_prefix(user_id)
    return sid == prefix or sid.startswith(f"{prefix}:")


def parse_canonical_session_id(session_id: str | None) -> Optional[int]:
    if not session_id or not str(session_id).startswith(CANONICAL_PREFIX):
        return None
    suffix = str(session_id)[len(CANONICAL_PREFIX) :]
    try:
        return int(suffix)
    except ValueError:
        return None


def seed_marketplace_session(session: Session, user: User) -> None:
    """Bind marketplace tool identity to the authenticated user (never trust LLM IDs)."""
    session.set("marketplace_user_id", user.id)
    session.set("marketplace_role", user.role)
    session.set("marketplace_subscription_status", user.subscription_status)


def seed_marketplace_session_by_id(
    session: Session,
    user_id: int,
    role: str,
    subscription_status: str,
) -> None:
    session.set("marketplace_user_id", user_id)
    session.set("marketplace_role", role)
    session.set("marketplace_subscription_status", subscription_status)
