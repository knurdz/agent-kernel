"""Gated Telegram webhook handler with update-ID deduplication.

The stock ``AgentTelegramRequestHandler`` already acknowledges Telegram before
processing (its route defers work to Starlette BackgroundTasks), but it has
two gaps this subclass closes, mirroring ``whatsapp_handler.py``:

1. **Dedup** — Telegram redelivers an update when the webhook does not answer
   2xx quickly; every redelivery re-ran the agent and sent another reply.
   Updates are registered by ``update_id`` (sync, race-free within one event
   loop turn) and duplicates dropped — same OrderedDict seen-set pattern as
   the WhatsApp handler's message IDs.
2. **Farmer-only subscription hard gate** — any chat could otherwise invoke
   the LLM. The gate looks the sender up by ``users.telegram_chat_id``;
   unlinked chats receive a contact-share keyboard (``request_contact``) and
   are linked to their existing marketplace account after a verified contact
   share. Non-farmers / inactive subscriptions get the signup-URL notice and
   never reach an agent. DB lookup failures fail open, like WhatsApp's gate.
"""

import json
import logging
import os
from collections import OrderedDict

from agentkernel.telegram import AgentTelegramRequestHandler
from sqlalchemy.exc import IntegrityError


class GatedTelegramHandler(AgentTelegramRequestHandler):
    """Deduplicates deliveries by update_id and gates non-farmers before the agent."""

    _SEEN_LIMIT = 1024

    def __init__(self):
        super().__init__()
        self._gate_log = logging.getLogger("agripilot.telegram")
        self._seen_ids: OrderedDict[int, None] = OrderedDict()

    # ------------------------------------------------------------------ dedup

    def _mark_update(self, body: dict) -> bool:
        """Register update_id, returning False for already-seen deliveries."""
        update_id = body.get("update_id")
        if update_id is None:
            return True
        if update_id in self._seen_ids:
            return False
        self._seen_ids[update_id] = None
        self._seen_ids.move_to_end(update_id)
        while len(self._seen_ids) > self._SEEN_LIMIT:
            self._seen_ids.popitem(last=False)
        return True

    # -------------------------------------------------------------- helpers

    def _skip_gate(self) -> bool:
        return os.environ.get("AK_MARKETPLACE__SKIP_SUBSCRIPTION_CHECK") == "1" or getattr(
            self, "_skip_marketplace_gate", False
        )

    def _signup_url(self) -> str:
        url = os.environ.get("AK_MARKETPLACE__SIGNUP_URL")
        if url and url.strip():
            return url.strip()
        try:
            import yaml

            with open("config.yaml", "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            cfg = (data.get("marketplace") or {}).get("signup_url")
            if isinstance(cfg, str) and cfg.strip():
                return cfg.strip()
        except Exception:  # noqa: BLE001 - cosmetic fallback only
            pass
        return "http://localhost:8000/docs"

    def _open_db(self):
        from marketplace.database import SessionLocal

        return SessionLocal()

    @staticmethod
    def _eligible(user) -> bool:
        return user is not None and user.role == "farmer" and user.subscription_status == "active"

    async def _send_link_prompt(self, chat_id) -> None:
        await self._send_message(
            chat_id,
            "AgriPilot is for active farmer accounts. Tap the button below to share your "
            "phone number and link your account.",
            reply_markup={
                "keyboard": [[{"text": "Share my phone number", "request_contact": True}]],
                "resize_keyboard": True,
                "one_time_keyboard": True,
            },
        )

    async def _send_signup_notice(self, chat_id) -> None:
        await self._send_message(
            chat_id,
            f"AgriPilot is for active farmer accounts. Sign up at {self._signup_url()}.",
        )

    # ------------------------------------------------------------- linking

    async def _link_via_contact(self, message: dict) -> None:
        """Link a verified contact share to the marketplace account, then confirm."""
        chat_id = (message.get("chat") or {}).get("id")
        contact = message.get("contact") or {}
        sender_id = (message.get("from") or {}).get("id")

        # A forwarded third-party contact must never link someone else's account.
        if contact.get("user_id") is not None and sender_id is not None:
            try:
                if int(contact["user_id"]) != int(sender_id):
                    self._gate_log.info("Telegram link refused chat=%s (contact/from mismatch)", chat_id)
                    await self._send_signup_notice(chat_id)
                    return
            except (TypeError, ValueError):
                await self._send_signup_notice(chat_id)
                return

        raw_phone = contact.get("phone_number")
        # Telegram sends phone_number without '+' (e.g. "94704512463") while
        # marketplace stores E.164 with '+'. Mirror whatsapp_handler.py:109-111:
        # ensure leading '+' before normalize_phone (which requires it).
        if isinstance(raw_phone, str):
            raw_phone = raw_phone.strip()
            if raw_phone and not raw_phone.startswith("+"):
                raw_phone = "+" + raw_phone.lstrip("+")
        self._gate_log.info(
            "telegram link attempt chat=%s sender=%s contact=%s raw_phone=%r",
            chat_id,
            sender_id,
            contact,
            raw_phone,
        )
        try:
            from marketplace.auth import normalize_phone

            normalized = normalize_phone(raw_phone)
            self._gate_log.info("telegram link normalized chat=%s -> %s", chat_id, normalized)
        except Exception as exc:  # noqa: BLE001 - unusable/missing phone -> re-prompt
            self._gate_log.info("telegram link normalize failed chat=%s raw=%r err=%s", chat_id, raw_phone, exc)
            await self._send_link_prompt(chat_id)
            return

        try:
            from sqlalchemy import select

            from marketplace.models import User

            db = self._open_db()
            try:
                user = db.scalars(select(User).where(User.phone_number == normalized)).first()
                if not self._eligible(user):
                    self._gate_log.info(
                        "Telegram link refused chat=%s role=%s sub=%s",
                        chat_id,
                        getattr(user, "role", None),
                        getattr(user, "subscription_status", None),
                    )
                    await self._send_signup_notice(chat_id)
                    return
                claimant = db.scalars(select(User).where(User.telegram_chat_id == int(chat_id))).first()
                if claimant is not None and claimant.id != user.id:
                    await self._send_message(
                        chat_id, "This Telegram account is already linked to another AgriPilot account."
                    )
                    return
                if user.telegram_chat_id is not None and user.telegram_chat_id != int(chat_id):
                    await self._send_message(
                        chat_id,
                        "This AgriPilot account is already linked to another Telegram chat. "
                        f"Manage your account at {self._signup_url()}.",
                    )
                    return
                display_name = user.name
                user.telegram_chat_id = int(chat_id)
                db.commit()
            finally:
                db.close()
            await self._send_message(chat_id, f"You're linked, {display_name}! Ask me anything about your crops.")
        except IntegrityError:
            self._gate_log.warning("Concurrent Telegram link race for chat=%s", chat_id)
            await self._send_message(chat_id, "This Telegram account is already linked to another AgriPilot account.")
        except Exception as exc:  # noqa: BLE001 - linking must never take the webhook down
            self._gate_log.warning("Telegram link failed for chat=%s: %s", chat_id, exc, exc_info=False)
            await self._send_link_prompt(chat_id)

    # ---------------------------------------------------------------- gate

    async def _process_webhook_body(self, body: dict) -> None:
        try:
            self._gate_log.debug("telegram raw body=%s", json.dumps(body, ensure_ascii=False, default=str))
        except Exception:  # noqa: BLE001
            self._gate_log.debug("telegram raw keys=%s", list(body.keys()))
        if not self._mark_update(body):
            self._gate_log.debug("Duplicate update %s dropped", body.get("update_id"))
            return

        if self._skip_gate():
            await self._delegate(body)
            return

        message = body.get("message")
        source = message or body.get("edited_message")
        if source is None:
            source = (body.get("callback_query") or {}).get("message")
        chat_id = ((source or {}).get("chat") or {}).get("id")

        if chat_id is None:
            await self._delegate(body)
            return

        try:
            from sqlalchemy import select

            from marketplace.models import User

            db = self._open_db()
            try:
                user = db.scalars(select(User).where(User.telegram_chat_id == int(chat_id))).first()
            finally:
                db.close()

            # Contact shares only matter while the chat is unlinked; afterwards a
            # forwarded contact is just an ordinary (non-text) message.
            if user is None and message is not None and isinstance(message.get("contact"), dict):
                await self._link_via_contact(message)
                return

            if self._eligible(user):
                await self._delegate(body)
                return

            if user is not None:
                self._gate_log.info(
                    "Telegram gate blocked chat=%s role=%s sub=%s", chat_id, user.role, user.subscription_status
                )
                await self._send_signup_notice(chat_id)
            else:
                await self._send_link_prompt(chat_id)
        except Exception as exc:  # noqa: BLE001 - fail open, matching the WhatsApp gate
            self._gate_log.warning("Telegram gate check failed for chat=%s: %s", chat_id, exc, exc_info=False)
            await self._delegate(body)

    async def _delegate(self, body: dict) -> None:
        """Hand a passing update to the stock pipeline (seam for tests)."""
        await super()._process_webhook_body(body)
