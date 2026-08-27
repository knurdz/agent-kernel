"""Fast-ack WhatsApp webhook handler with message-ID deduplication.

The stock AgentWhatsAppRequestHandler awaits the full agent run inside the
webhook POST and only then returns 200. Meta's Cloud API times a webhook out
after ~10 s and redelivers — every redelivery re-ran the agent and sent
another reply (visible as repeated 2a03:2880:* POSTs in the access log).
This subclass returns 200 immediately after verifying the signature and
registering the incoming message IDs, then processes each new message as a
background asyncio task. Already-seen IDs are dropped, so late redeliveries
are ignored even if they slip past the timeout window.
"""

import asyncio
import logging
import os
import traceback
from collections import OrderedDict

from agentkernel.core.model import AgentRequestFile, AgentRequestImage, AgentRequestText, BaseChatRequest
from agentkernel.whatsapp import AgentWhatsAppRequestHandler
from fastapi import HTTPException, Request

from marketplace.session_identity import canonical_session_id, seed_marketplace_session


class FastAckWhatsAppHandler(AgentWhatsAppRequestHandler):
    """Deduplicates deliveries and acknowledges Meta before processing."""

    _SEEN_LIMIT = 1024

    def __init__(self):
        super().__init__()
        self._log = logging.getLogger("agripilot.whatsapp")
        self._seen_ids: OrderedDict[str, None] = OrderedDict()

    def _mark_and_filter(self, body: dict) -> list[tuple[dict, dict]]:
        """Return unseen (message, value) pairs from the payload, marking them seen.

        Runs without awaits, so concurrent webhook deliveries cannot race past
        the check: within one event loop turn an ID is either registered or not.
        """
        pending: list[tuple[dict, dict]] = []
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for message in value.get("messages", []):
                    message_id = message.get("id")
                    if not message_id or message_id in self._seen_ids:
                        continue
                    self._seen_ids[message_id] = None
                    self._seen_ids.move_to_end(message_id)
                    while len(self._seen_ids) > self._SEEN_LIMIT:
                        self._seen_ids.popitem(last=False)
                    pending.append((message, value))
        return pending

    async def _send_whatsapp_text(self, to: str, body: str) -> None:
        """Best-effort send via Graph API; stub logs when creds missing."""
        phone_id = os.environ.get("AK_WHATSAPP__PHONE_NUMBER_ID") or getattr(self, "_phone_number_id", None)
        token = os.environ.get("AK_WHATSAPP__ACCESS_TOKEN") or getattr(self, "_access_token", None)
        if not phone_id or not token or not to:
            self._log.info("whatsapp gate stub: to=%s body=%s", to, body[:80])
            return
        url = f"https://graph.facebook.com/v20.0/{phone_id}/messages"
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=headers, json=payload, timeout=5)
                self._log.info("whatsapp gate sent to %s status %s", to, getattr(resp, "status_code", "?"))
        except Exception as exc:  # noqa: BLE001
            self._log.warning("whatsapp gate send failed to %s: %s", to, exc, exc_info=False)

    async def _handle_webhook(self, request: Request) -> dict:
        if self._app_secret:
            signature = request.headers.get("x-hub-signature-256", "")
            if not self._verify_signature(await request.body(), signature):
                self._log.warning("Invalid request signature")
                raise HTTPException(status_code=403, detail="Invalid signature")

        body = await request.json()
        if body.get("object") != "whatsapp_business_account":
            return {"status": "ok"}

        pending = self._mark_and_filter(body)
        # Subscription gate per entry (farmer-only, WhatsApp hard gate) — bypass when SKIP=1 (dev/test) or handler flagged
        if os.environ.get("AK_MARKETPLACE__SKIP_SUBSCRIPTION_CHECK") == "1" or getattr(
            self, "_skip_marketplace_gate", False
        ):
            for message, value in pending:
                asyncio.create_task(self._process_message(message, value))
            return {"status": "ok"}
        filtered: list[tuple[dict, dict]] = []
        for message, value in pending:
            # wa_id from contacts (preferred) or message from
            wa_id = None
            try:
                contacts = value.get("contacts") or []
                if contacts and isinstance(contacts, list):
                    wa_id = contacts[0].get("wa_id")
                if not wa_id:
                    wa_id = message.get("from")
                # Normalize to E.164 for lookup (strip, add +, re-normalize)
                normalized = None
                if wa_id:
                    raw = str(wa_id).strip()
                    if not raw.startswith("+"):
                        raw = "+" + raw.lstrip("+")
                    try:
                        from marketplace.auth import normalize_phone

                        normalized = normalize_phone(raw)
                    except Exception:
                        normalized = None
                if normalized:
                    # Lookup user
                    from sqlalchemy import select

                    from marketplace.database import SessionLocal
                    from marketplace.models import User

                    db = SessionLocal()
                    try:
                        user = db.scalars(select(User).where(User.phone_number == normalized)).first()
                    finally:
                        db.close()
                    if (
                        not user
                        or user.role != "farmer"
                        or (
                            user.subscription_status != "active"
                            and os.environ.get("AK_MARKETPLACE__SKIP_SUBSCRIPTION_CHECK") != "1"
                        )
                    ):
                        signup_url = os.environ.get("AK_MARKETPLACE__SIGNUP_URL") or "http://localhost:8000/docs"
                        try:
                            from config import get_config  # type: ignore

                            cfg_url = (
                                get_config().get("marketplace.signup_url") if hasattr(get_config(), "get") else None
                            )
                            if cfg_url:
                                signup_url = cfg_url
                        except Exception:
                            pass
                        # Try config.yaml fallback
                        if signup_url == "http://localhost:8000/docs":
                            try:
                                import yaml

                                with open("config.yaml", "r", encoding="utf-8") as fh:
                                    data = yaml.safe_load(fh) or {}
                                cfg = (data.get("marketplace") or {}).get("signup_url")
                                if isinstance(cfg, str) and cfg.strip():
                                    signup_url = cfg.strip()
                            except Exception:
                                pass
                        # Use normalized wa_id as To if available, else raw from
                        to = normalized or wa_id or message.get("from")
                        await self._send_whatsapp_text(
                            to=to,
                            body=f"AgriPilot WhatsApp is for active farmer accounts. Sign up at {signup_url}.",
                        )
                        self._log.info(
                            "WhatsApp gate blocked wa_id=%s role=%s sub=%s",
                            wa_id,
                            getattr(user, "role", None) if user else None,
                            getattr(user, "subscription_status", None) if user else None,
                        )
                        continue
                # Passing case: keep for processing
                filtered.append((message, value))
            except Exception as exc:  # noqa: BLE001
                self._log.warning("WhatsApp gate check failed for wa_id %s: %s", wa_id, exc, exc_info=False)
                filtered.append((message, value))
        for message, value in filtered:
            asyncio.create_task(self._process_message(message, value))
        return {"status": "ok"}

    async def _process_message(self, message: dict, value: dict) -> None:
        try:
            await self._handle_message(message, value)
        except Exception:  # noqa: BLE001 - background task must never crash the server
            self._log.exception(f"Background processing failed for message {message.get('id')}")

    def _lookup_active_farmer(self, wa_id: str | None):
        if not wa_id:
            return None
        try:
            raw = str(wa_id).strip()
            if not raw.startswith("+"):
                raw = "+" + raw.lstrip("+")
            from marketplace.auth import normalize_phone
            from sqlalchemy import select

            from marketplace.database import SessionLocal
            from marketplace.models import User

            normalized = normalize_phone(raw)
            db = SessionLocal()
            try:
                user = db.scalars(select(User).where(User.phone_number == normalized)).first()
            finally:
                db.close()
            if user and user.role == "farmer" and user.subscription_status == "active":
                return user
        except Exception:
            return None
        return None

    async def _handle_message(self, message: dict, value: dict):
        """Handle WhatsApp message with unified agri:user:{id} session when farmer matched."""
        message_id = message.get("id")
        from_number = message.get("from")
        message_type = message.get("type")

        if not from_number or not message_id:
            self._log.warning("Message missing required fields (from/id)")
            return

        self._log.debug("Processing message %s from %s of type %s", message_id, from_number, message_type)
        requests = []
        text = None
        if message_type == "text":
            text = message.get("text", {}).get("body")
        elif message_type == "interactive":
            interactive = message.get("interactive", {})
            if interactive.get("type") == "button_reply":
                text = interactive.get("button_reply", {}).get("title")
            elif interactive.get("type") == "list_reply":
                text = interactive.get("list_reply", {}).get("title")
        elif message_type == "image":
            image_info = message.get("image", {})
            caption = image_info.get("caption", "")
            text = caption if caption else "[Image received]"
            media_id = image_info.get("id")
            if media_id:
                media_size, media_mime_type = await self._get_media_info(media_id)
                if media_size is None:
                    await self._send_message(
                        from_number, "Sorry, I could not retrieve the image information. Please try again.", message_id
                    )
                    return
                if media_size > self._max_file_size:
                    await self._send_message(
                        from_number,
                        f"Sorry, the image file size ({media_size / (1024 * 1024):.2f} MB) exceeds the maximum allowed size of {self._max_file_size / (1024 * 1024):.2f} MB.",
                        message_id,
                    )
                    return
                image_data = await self._download_media(media_id)
                if image_data is None:
                    await self._send_message(from_number, "Sorry, I could not download the image. Please try again.", message_id)
                    return
                requests.append(
                    AgentRequestImage(
                        image_data=image_data,
                        name=f"whatsapp_image_{message_id}",
                        mime_type=media_mime_type or image_info.get("mime_type", "image/jpeg"),
                    )
                )
        elif message_type == "document":
            document_info = message.get("document", {})
            caption = document_info.get("caption", "")
            filename = document_info.get("filename", "document")
            text = caption if caption else f"[Document received: {filename}]"
            media_id = document_info.get("id")
            if media_id:
                media_size, media_mime_type = await self._get_media_info(media_id)
                if media_size is None:
                    await self._send_message(
                        from_number,
                        f"Sorry, I could not retrieve the document '{filename}' information. Please try again.",
                        message_id,
                    )
                    return
                if media_size > self._max_file_size:
                    await self._send_message(
                        from_number,
                        f"Sorry, the document '{filename}' size ({media_size / (1024 * 1024):.2f} MB) exceeds the maximum allowed size of {self._max_file_size / (1024 * 1024):.2f} MB.",
                        message_id,
                    )
                    return
                file_data = await self._download_media(media_id)
                if file_data is None:
                    await self._send_message(
                        from_number,
                        f"Sorry, I could not download the document '{filename}'. Please try again.",
                        message_id,
                    )
                    return
                requests.append(
                    AgentRequestFile(
                        file_data=file_data,
                        name=filename,
                        mime_type=media_mime_type or document_info.get("mime_type"),
                    )
                )
        elif message_type in ["video", "audio"]:
            await self._send_message(from_number, "Sorry, audio and video messages are not supported yet.", message_id)
            return

        if not text:
            self._log.warning("Unsupported message type: %s", message_type)
            return

        requests.insert(0, AgentRequestText(prompt=text))
        farmer = self._lookup_active_farmer(from_number)
        if farmer:
            session_id = canonical_session_id(farmer.id)
            acting_user = str(farmer.id)
        else:
            session_id = from_number
            acting_user = from_number

        try:
            if self._whatsapp_agent_acknowledgement:
                await self._send_message(from_number, self._whatsapp_agent_acknowledgement, message_id)
            req = BaseChatRequest(
                prompt=text,
                agent=self._whatsapp_agent,
                session_id=session_id,
                user_id=acting_user,
            )
            try:
                result, loaded_sid = await self._chat_service.execute(req, requests=requests)
            except ValueError as ve:
                self._log.warning("Agent execution rejected: %s (session_id: %s)", ve, session_id)
                await self._send_message(from_number, "Sorry, no agent is available to handle your request.", message_id)
                return
            if farmer:
                try:
                    from agentkernel.core.runtime import Runtime

                    runtime = Runtime.current()
                    session = runtime.sessions().load(loaded_sid or session_id)
                    if session is not None:
                        seed_marketplace_session(session, farmer)
                        await runtime.sessions().store(session)
                except Exception:
                    pass
            await self._send_message(from_number, str(result), message_id)
        except Exception as exc:  # noqa: BLE001
            self._log.error("Error handling message: %s\n%s", exc, traceback.format_exc())
            await self._send_message(from_number, "Sorry, there was an error processing your request.", message_id)
