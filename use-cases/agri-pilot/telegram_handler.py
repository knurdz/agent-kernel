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
import traceback
from collections import OrderedDict

from agentkernel.core.model import AgentRequestText, BaseChatRequest
from agentkernel.telegram import AgentTelegramRequestHandler
from sqlalchemy.exc import IntegrityError

from marketplace.session_identity import canonical_session_id, seed_marketplace_session


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

        # Mobile deep-link token linking (/start <token>)
        if message is not None and isinstance(message.get("text"), str) and message["text"].startswith("/start "):
            if await self._try_link_via_start_token(message):
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

    async def _process_agent_message(self, chat_id: int, message_text: str, message: dict | None = None):
        """Process message through agent with unified session id when linked farmer."""
        from agentkernel.core.model import AgentRequestText

        farmer = None
        try:
            from sqlalchemy import select

            from marketplace.models import User

            db = self._open_db()
            try:
                farmer = db.scalars(select(User).where(User.telegram_chat_id == int(chat_id))).first()
            finally:
                db.close()
        except Exception:
            farmer = None

        if farmer and self._eligible(farmer):
            session_id = canonical_session_id(farmer.id)
            acting_user = str(farmer.id)
        else:
            session_id = str(chat_id)
            acting_user = str((message or {}).get("from", {}).get("id") or chat_id)

        sender_id = (message or {}).get("from", {}).get("id")
        try:
            await self._send_chat_action(chat_id, "typing")
            requests = []
            if message_text:
                requests.append(AgentRequestText(prompt=message_text))
            if message:
                failed_files = await self._process_files(message, requests)
                if failed_files:
                    self._gate_log.warning("Failed to process files: %s", failed_files)
            if not requests:
                await self._send_message(chat_id, "Sorry, your message appears to be empty.")
                return
            req = BaseChatRequest(
                prompt=message_text,
                agent=self._telegram_agent,
                session_id=session_id,
                user_id=acting_user,
            )
            try:
                result, loaded_sid = await self._chat_service.execute(req, requests=requests)
            except ValueError as ve:
                self._gate_log.warning("Agent execution rejected: %s (session_id: %s)", ve, session_id)
                await self._send_message(chat_id, "Sorry, no agent is available to handle your request.")
                return
            if farmer and self._eligible(farmer):
                try:
                    from agentkernel.core.runtime import Runtime

                    runtime = Runtime.current()
                    session = runtime.sessions().load(loaded_sid or session_id)
                    if session is not None:
                        seed_marketplace_session(session, farmer)
                        await runtime.sessions().store(session)
                except Exception:
                    pass
            await self._send_message(chat_id, str(result))
        except Exception as exc:  # noqa: BLE001
            self._gate_log.error("Error handling message: %s\n%s", exc, traceback.format_exc())
            await self._send_message(chat_id, "Sorry, there was an error processing your request.")

    async def _try_link_via_start_token(self, message: dict) -> bool:
        """Link farmer account when user sends /start <token> from mobile deep link."""
        text = (message.get("text") or "").strip()
        if not text.startswith("/start"):
            return False
        parts = text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            return False
        token = parts[1].strip()
        chat_id = (message.get("chat") or {}).get("id")
        if chat_id is None:
            return False
        try:
            from marketplace.channels import consume_telegram_link_token

            user = consume_telegram_link_token(token, int(chat_id))
            if user:
                await self._send_message(chat_id, f"Telegram linked to your AgriPilot account, {user.name}!")
                return True
            await self._send_message(chat_id, "That link is invalid or expired. Generate a new link in the app.")
            return True
        except Exception as exc:  # noqa: BLE001
            self._gate_log.warning("Telegram token link failed chat=%s: %s", chat_id, exc)
            return False
