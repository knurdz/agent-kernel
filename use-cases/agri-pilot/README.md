# AgriPilot

Agentic AI agricultural assistant for smallholder farmers, built on [Agent Kernel](https://github.com/yaalalabs) with **LangGraph** (`agentkernel.langgraph`).

`AGENTS.md` covers conventions for coding agents working in this directory.

## Architecture

Supervisor `agents/supervisor.py:27` routes each message to four specialists: `vision_agent` (crop-disease diagnosis), `knowledge_agent` (agricultural RAG over ChromaDB `data/chroma_db/`), `resource_agent` (weather + irrigation via `tools/weather_tool.py:1` Open-Meteo), and `delivery_agent` (read-only order/dispatch status via `tools/delivery_tools.py`). Price/selling questions get honest "no market prices" reply — market specialist removed 2026-08-24 (no reliable API).

Two code-level backstops wrap LLM prompts: `agents/supervisor_guardrails.py:47` (handoff-loop + narrated-action LLM judge, `AGRIPILOT_JUDGE_PROVIDER`) and `agents/knowledge_guardrails.py` (no chemical/dosage without `allow` from `tools/safety_tool.py:1` `validate_treatment` vs `data/safety_rules.json`). Data-fetching tools are wrapped by `tools/tool_guard.py:100` (`@guarded`, per-session `AGRIPILOT_TOOL_MAX_CALLS=8`, `AGRIPILOT_TOOL_TIMEOUT_SECONDS=180`, `contextvars.copy_context`).

Marketplace adds `marketplace/` (DB, auth, service, `notifications.py`, `routers/auth.py` `/api/auth`, `routers/farmer.py` `/api/farmer`, `routers/buyer.py` `/api/buyer`) + chat tools `tools/marketplace_tools.py:130` (6 `@guarded` tools bound to supervisor `agents/supervisor.py:29`). Runtime backend is **Postgres-only** (`AK_MARKETPLACE__DATABASE_URL` > `config.yaml` > `postgresql+psycopg://agripilot:agripilot@localhost:5432/agripilot`); `app.py:23` runs Alembic migrations (`marketplace.database.run_migrations()`) at startup, so schema authority is `migrations/`. Legacy SQLite `data/app.db` is read only by `scripts/migrate_sqlite_to_postgres.py`.

Durable memory: sessions and multimodal attachments are Redis-backed under Docker (`AK_SESSION__*` / `AK_MULTIMODAL__*` overrides on the compose `redis` service), so conversations survive container restarts — over WhatsApp the sender's phone number *is* the session id. `state/farmer_profile.py` + `tools/profile_tools.py` keep a per-session case history (crop, disease, severity, advice, date, follow-up status); vision records diagnoses, knowledge records validated advice, and triage Step 2b resolves "it"/"getting worse" against the stored profile instead of re-asking.

**Plant tracking & crop scans:** farmers can run a **one-time crop scan** (`POST /api/farmer/scans`) or maintain a **plant list** with a photo timeline (`/api/farmer/plants*`). Image analysis reuses the existing HuggingFace ViT pipeline in `tools/vision_tool.py` (`check_image_quality` + `diagnose_crop_image` via `analyze_crop_photo`) — no separate vision API. Observation photos persist on disk under `data/plant_media/` (Docker volume `plant-media`; override with `AGRIPILOT_PLANT_MEDIA_ROOT`). A sell listing can be linked 1:1 to a tracked plant (`POST /api/farmer/listings/{id}/import-plant`); buyers then see **crop-health insights** on that listing (`GET /api/buyer/listings/{id}/insights`) — observation counts, diagnosis timeline, and trend — without raw photos or chemical advice. Chat diagnosis (supervisor → vision → knowledge) remains unchanged for conversational advice.

**Listing shop:** farmers can attach a **product photo** when creating or editing a listing (`POST /api/farmer/listings/{id}/photo`); images persist under `data/listing_media/` (Docker volume `listing-media`; override with `AGRIPILOT_LISTING_MEDIA_ROOT`). Listings support **category** (`vegetable|fruit|grain|spice|other`), optional **description**, and **harvest date**. Farmers manage stock, status, and view **analytics** (`GET /api/farmer/listings/{id}/analytics` — views, connection requests, orders, kg sold, revenue estimate). Buyers auto-browse all active listings (empty filters return the full feed); crop search uses case-insensitive substring match; optional `category` filter. Opening a listing detail increments `view_count`.

**Rider delivery MVP:** a third **rider** account (self-registered with vehicle confirmation) can accept nearby delivery jobs after farmers mark orders ready. Buyers choose **pickup** or **delivery** on accepted connections; farmers confirm quantity and pickup pin; delivery orders enter rider search by weight + distance (no vehicle-type tiers). State changes are **deterministic REST** (`marketplace/order_service.py`, `marketplace/dispatch_service.py`); the agent only explains status via read-only `delivery_tools`. Maps use **OpenStreetMap** tiles in the mobile app (`flutter_map`, no API key) and optional **OSRM** road routing on the server (`marketplace/maps_service.py`, falls back to Haversine). Live tracking uses rider GPS posts + buyer/farmer polling; FCM notifies milestones. Payment stays cash/off-platform.

## Prerequisites

- Python `>=3.12`, `uv` (see `pyproject.toml:6`)
- One LLM key: `OPENAI_API_KEY` or `GEMINI_API_KEY` or `OPENROUTER_API_KEY` (auto-detected, `AGRIPILOT_MODEL_PROVIDER` to force)
- For `app.py` / WhatsApp: `AK_WHATSAPP__ACCESS_TOKEN`, `AK_WHATSAPP__PHONE_NUMBER_ID`, `AK_WHATSAPP__VERIFY_TOKEN` (Meta Cloud API). For marketplace JWT: `AK_MARKETPLACE__JWT_SECRET` (≥32 chars in prod).

## Setup

```bash
cp .env.local.example .env.local   # fill at least one provider key (+ WhatsApp/JWT if using app.py)
./build.sh                         # uv venv && uv sync (also uv run python scripts/ingest_knowledge.py if you edit data/knowledge_docs/)
# Bare-metal dev (in-memory session/attachment stores; pytest needs no Docker)
OPENAI_API_KEY=sk-dummy uv run pytest -m "not slow"   # dummy key enough for unit tests
python demo.py                      # CLI (LangGraphModule)
uv run python app.py                # REST + WhatsApp webhook (needs Postgres for marketplace + WhatsApp env)
# Docker: app + Postgres + Redis, durable sessions and attachments
docker compose up --build           # app at http://localhost:8000
# Android mobile app (see mobile/README.md)
cd mobile && flutter pub get && flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

## Mobile app (Android)

The Flutter client lives in [`mobile/`](mobile/). It uses **JWT-authenticated** agent chat (`POST /api/v1/chat*`), thread history (`GET /api/v1/threads*`), marketplace REST, profile/channel management, and optional FCM push. Unified agent sessions use `agri:user:{user_id}` across mobile, WhatsApp, and Telegram.

New API surfaces (mobile):

| Method | Path | Auth |
|--------|------|------|
| `PATCH` | `/api/auth/me` | JWT |
| `GET` | `/api/auth/me/channels` | JWT |
| `POST` | `/api/auth/me/channels/telegram/link-token` | JWT farmer |
| `DELETE` | `/api/auth/me/channels/telegram` | JWT farmer |
| `GET` | `/api/config/public` | public |
| `POST` | `/api/devices/register` | JWT |
| `DELETE` | `/api/devices/unregister` | JWT |
| `GET/PATCH` | `/api/devices/notification-preferences` | JWT |
| `POST` | `/api/farmer/scans` | JWT farmer+active |
| `GET/POST` | `/api/farmer/plants` | JWT farmer+active |
| `GET` | `/api/farmer/plants/{id}` | JWT farmer+active |
| `POST` | `/api/farmer/plants/{id}/observations` | JWT farmer+active |
| `GET` | `/api/farmer/plants/{id}/observations/{obs_id}/photo` | JWT farmer+active |
| `POST` | `/api/farmer/listings/{id}/import-plant` | JWT farmer+active |
| `GET` | `/api/buyer/listings/{id}/insights` | JWT buyer |
| `POST` | `/api/buyer/orders` | JWT buyer |
| `GET` | `/api/buyer/orders` | JWT buyer |
| `GET` | `/api/buyer/orders/{id}/tracking` | JWT buyer |
| `POST` | `/api/farmer/orders/{id}/confirm` | JWT farmer+active |
| `POST` | `/api/farmer/orders/{id}/ready` | JWT farmer+active |
| `GET/POST` | `/api/rider/jobs`, `/api/rider/online`, `/api/rider/location` | JWT rider |
| `POST` | `/api/rider/jobs/{order_id}/accept` | JWT rider |

Mobile rider setup: `flutter run --dart-define=API_BASE_URL=...` — no map API keys required. Signup role **Rider** requires the vehicle checkbox.

`demo.py:5` calls `load_dotenv(".env.local")` **before** importing `agentkernel` — keep that order in new entrypoints. `AK_` env vars override `config.yaml` with `__` nesting (e.g. `AK_GUARDRAIL__INPUT__ENABLED=false`, `AK_MARKETPLACE__SKIP_SUBSCRIPTION_CHECK=1` dev bypass).

Key `.env.local.example:78` knobs:

| Var | Purpose |
|-----|---------|
| `AK_MARKETPLACE__DATABASE_URL` | `postgresql+psycopg://...` (only runtime backend; compose wires it to the `db` service) |
| `AK_SESSION__TYPE` / `AK_SESSION__REDIS__URL` | Redis session store (compose sets `redis`; unset = in-memory bare-metal dev) |
| `AK_MULTIMODAL__STORAGE_TYPE` / `AK_MULTIMODAL__REDIS__URL` | Redis attachment storage so photos survive restarts (unset = in-memory) |
| `AK_MARKETPLACE__JWT_SECRET` | HS256 secret (fallback `config.yaml:32` dev-only) |
| `AK_MARKETPLACE__JWT_EXPIRY_HOURS` | default `24` |
| `AK_MARKETPLACE__SIGNUP_URL` | WhatsApp rejection link (`http://localhost:8000/docs` default) |
| `AK_MARKETPLACE__SKIP_SUBSCRIPTION_CHECK` | `1` bypasses farmer `active` gate (dev/tests, never prod) |
| `AK_MARKETPLACE__DEV_USER_ID` | inject marketplace identity into `demo.py` chat without JWT (dev) |
| `AK_WHATSAPP__ACCESS_TOKEN` / `PHONE_NUMBER_ID` / `VERIFY_TOKEN` / `APP_SECRET` | Cloud API (see `API / WhatsApp` below) |
| `AK_TELEGRAM__BOT_TOKEN` / `AK_TELEGRAM__WEBHOOK_SECRET` | Telegram Bot API — token from @BotFather; secret echoed back as `X-Telegram-Bot-Api-Secret-Token` (see `API / Telegram`) |
| `AGRIPILOT_TOOL_MAX_CALLS` / `AGRIPILOT_TOOL_TIMEOUT_SECONDS` | `tools/tool_guard.py:44` limits |
| `AGRIPILOT_PLANT_MEDIA_ROOT` | default `data/plant_media/` — on-disk plant observation photos (Docker volume `plant-media`) |
| `AGRIPILOT_LISTING_MEDIA_ROOT` | default `data/listing_media/` — on-disk listing product photos (Docker volume `listing-media`) |

## Marketplace — Roles & Auth

- **Roles:** `farmer` (sells, WhatsApp+REST, `subscription_status` `active|expired|none`), `buyer` (browses/connects, JWT-only, **no** subscription per 2026-08-25), `admin` via `scripts/seed_admin.py` only.
- **Phone:** `E.164` `^\+[1-9]\d{7,14}$` (`marketplace/auth.py:25` `normalize_phone` strips spaces/dashes). Farmer may set optional `contact_phone_number` (buyer-facing, fallback to primary `users.phone_number` `marketplace/models.py:48`) — revealed only via `GET .../contact` after `accepted`.
- **JWT:** `HS256` `Authorization: Bearer <JWT>` (`marketplace/auth.py:75` `create_access_token`, `91` `get_current_user` via `HTTPBearer`). `decode_token` 401 on expired/invalid.
- **Subscription:** Farmer `active` required for all `/api/farmer/*` (`marketplace/routers/farmer.py:41` `_farmer_active`, `marketplace/auth.py:120` `require_active_subscription`); buyer routes JWT-only (including `POST /buyer/.../connect`). WhatsApp hard gate blocks non-`farmer`/`active` before agent (`whatsapp_handler.py:52` `_handle_webhook`, `_send_whatsapp_text`); the Telegram hard gate does the same by linked `users.telegram_chat_id` (`telegram_handler.py`, see `API / Telegram`).

### Quickstart (bash)

```bash
BASE=http://localhost:8000
# Farmer with buyer-facing contact phone
curl -s $BASE/api/auth/signup -H 'Content-Type: application/json' \
  -d '{"role":"farmer","phone_number":"+94770000001","password":"secret123","name":"Amal","district":"Kandy","contact_phone_number":"+94770000901"}'
curl -s $BASE/api/auth/login -H 'Content-Type: application/json' \
  -d '{"phone_number":"+94770000001","password":"secret123"}' # -> {access_token}
F_TOKEN=<jwt>

# Buyer
curl -s $BASE/api/auth/signup -H 'Content-Type: application/json' \
  -d '{"role":"buyer","phone_number":"+94770000002","password":"secret123","name":"Nimal","district":"Colombo","business_name":"Shop"}'
curl -s $BASE/api/auth/login -H 'Content-Type: application/json' \
  -d '{"phone_number":"+94770000002","password":"secret123"}'
B_TOKEN=<jwt>

# Me (farmer shows contact_phone)
curl -s $BASE/api/auth/me -H "Authorization: Bearer $F_TOKEN"

# Farmer CRUD (all require farmer active)
curl -s $BASE/api/farmer/listings -H "Authorization: Bearer $F_TOKEN" -H 'Content-Type: application/json' \
  -d '{"crop":"tomato","quantity_kg":500,"price_per_kg":120}'       # 201 {id, crop: "tomato" lowercased}
curl -s "$BASE/api/farmer/listings?status=active&limit=20&offset=0" -H "Authorization: Bearer $F_TOKEN"
curl -s -X PATCH $BASE/api/farmer/listings/1 -H "Authorization: Bearer $F_TOKEN" -H 'Content-Type: application/json' \
  -d '{"status":"sold"}'   # active->sold|expired|cancelled, 400 if sold->active
curl -s -X DELETE $BASE/api/farmer/listings/1 -H "Authorization: Bearer $F_TOKEN" # 204
```

## Endpoint Reference (26 distinct methods)

**Agent Kernel default** (`ak-py/src/agentkernel/api/http.py:59`, `handler.py:150`, `whatsapp_chat.py:46` — mounted even without `RESTAPI.add_auth_handlers`):

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| `GET` | `/health` | none | `{"status":"ok"}` |
| `GET` | `/openapi.json`, `/docs`, `/redoc` | none | FastAPI docs |
| `GET` | `/api/v1/agents` | none | list (`triage`) |
| `POST` | `/api/v1/chat` | none | `{"prompt","session_id","agent":"triage"}` → agent reply (JSON) |
| `POST` | `/api/v1/chat-multipart` | none | `multipart/form-data` + files/images (10 MB `config.yaml:42`) |
| `GET` | `/whatsapp/webhook?hub.mode&hub.verify_token&hub.challenge` | `AK_WHATSAPP__VERIFY_TOKEN` | returns challenge or 403 |
| `POST` | `/whatsapp/webhook` | `X-Hub-Signature-256` + farmer `active` gate | dedup `_SEEN_LIMIT=1024`, `{"status":"ok"}` immediately |
| `POST` | `/telegram/webhook` | `X-Telegram-Bot-Api-Secret-Token` == `AK_TELEGRAM__WEBHOOK_SECRET` + farmer gate via `users.telegram_chat_id` | update-ID dedup, `{"ok":true}` immediately; unlinked chats get contact-share link keyboard |

**Marketplace — `RESTAPI.add()` (`app.py:27`, `config.yaml:37` no `/custom` prefix)**

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/auth/signup` | public | `SignupRequest{role,phone_number,password≥8,name,district?,contact_phone_number? (farmer E.164)}` → `201 {id,phone_number,role,subscription_status}`; `409` duplicate; buyer `none`, farmer `active` |
| `POST` | `/api/auth/login` | public | `LoginRequest{phone_number,password}` → `200 {access_token}`; `401` |
| `GET` | `/api/auth/me` | `Bearer JWT` | `MeResponse{id,phone_number,role,subscription_status,profile:{district,contact_phone}}` |
| `POST` | `/api/farmer/listings` | `farmer+active` | `ListingCreate{crop,quantity_kg>0,price_per_kg≥0?,harvest_date?,category?,description?}` → `201 ListingResponse` (crop lowercased) |
| `GET` | `/api/farmer/listings?status&limit&offset` | `farmer+active` | own `PaginatedListings{items,total,limit,offset}` `created_at DESC` |
| `GET` | `/api/farmer/listings/{id}` | `farmer+active` owner | full `ListingResponse` incl. `available_kg`, `reserved_quantity_kg`, `photo_url` |
| `GET` | `/api/farmer/listings/{id}/analytics` | `farmer+active` owner | views, connection counts, orders, kg sold, revenue estimate |
| `POST` | `/api/farmer/listings/{id}/photo` | `farmer+active` owner | multipart `image` → `200 ListingResponse` with `photo_url` |
| `GET` | `/api/farmer/listings/{id}/photo` | `farmer+active` owner | JPEG/PNG product photo |
| `PATCH` | `/api/farmer/listings/{id}` | `farmer+active` owner | `ListingUpdate{crop?,quantity_kg?,price_per_kg?,harvest_date?,status?,category?,description?}` → `200` or `404`/`400`/`422` |
| `DELETE` | `/api/farmer/listings/{id}` | `farmer+active` owner | `204` or `404` |
| `GET` | `/api/farmer/connections` | `farmer+active` | inbox `[ConnectionWithListingAndBuyer]` (buyer `name,district,business_name`, no `phone_number`) |
| `PATCH` | `/api/farmer/connections/{id}` | `farmer+active` owner | `{"status":"accepted"\|"declined"\|"completed"}` `200 ConnectionResponse` `422`/`400` terminal/`404` |
| `GET` | `/api/farmer/connections/{id}/contact` | `farmer+active` owner | `200 ContactResponse{phone_number (buyer primary),listing_id,connection_id,status}` only `accepted`/`completed` else `400` |
| `GET` | `/api/buyer/listings?crop&district&category&min_qty&max_price&limit&offset` | `buyer` | active `PaginatedListings` (empty filters = all active; `crop` ILIKE substring; `category` exact; `district` join `farmer_profiles.district` case-insensitive); includes `farmer_name`, `district`, `available_kg`, `photo_url`; no phone |
| `GET` | `/api/buyer/listings/{id}` | `buyer` | active `ListingResponse` (increments `view_count`) or `404` |
| `GET` | `/api/buyer/listings/{id}/photo` | `buyer` | product photo for active listing |
| `GET` | `/api/buyer/match?crop=&quantity_kg=&district=` | `buyer` | ranked `MatchResponse{items:[{listing,score,reason}],query}` (`exact 2`, `same region 1` via `data/districts.json:1` else `0`, `-created_at`, `quantity_kg>=requested` filter then score); `crop` required `422` |
| `POST` | `/api/buyer/listings/{id}/connect` | `buyer` | `ConnectionCreate{message?≤500}` → `201 ConnectionResponse pending` `409` duplicate pending, `404` inactive, best-effort `marketplace/notifications.py:7` WhatsApp to farmer |
| `GET` | `/api/buyer/connections` | `buyer` | own `[ConnectionWithListing]` (no phone) |
| `GET` | `/api/buyer/connections/{id}/contact` | `buyer` owner | `ContactResponse{phone_number (farmer contact_phone or primary),...}` only `accepted`/`completed` |
| `POST` | `/api/farmer/scans` | `farmer+active` | multipart `image` + optional `crop` → `ScanResult` (one-time ViT analysis; does not create a plant) |
| `GET/POST` | `/api/farmer/plants` | `farmer+active` | list/create tracked plants (`PlantCreate{crop,name?,planted_on?,listing_id?}`) |
| `GET` | `/api/farmer/plants/{id}` | `farmer+active` | plant detail + observations + derived insights |
| `POST` | `/api/farmer/plants/{id}/observations` | `farmer+active` | multipart photo → analyze + append observation |
| `GET` | `/api/farmer/plants/{id}/observations/{obs_id}/photo` | `farmer+active` | farmer-only observation photo |
| `POST` | `/api/farmer/listings/{id}/import-plant` | `farmer+active` | create plant from listing crop; 1:1 link (`409` if already linked) |
| `GET` | `/api/buyer/listings/{id}/insights` | `buyer` | public crop-health summary when listing linked to tracked plant; `404` otherwise (no photos/chemicals) |

### Buyer flow curl

```bash
curl -s "$BASE/api/buyer/listings?crop=tomato&district=Kandy&min_qty=400&max_price=150&limit=20&offset=0" -H "Authorization: Bearer $B_TOKEN"
curl -s "$BASE/api/buyer/listings/1" -H "Authorization: Bearer $B_TOKEN" # no phone_number in JSON
curl -s "$BASE/api/buyer/match?crop=tomato&quantity_kg=300&district=Kandy" -H "Authorization: Bearer $B_TOKEN"
# connect
curl -s -X POST $BASE/api/buyer/listings/1/connect -H "Authorization: Bearer $B_TOKEN" -H 'Content-Type: application/json' -d '{"message":"need 200kg"}'
curl -s $BASE/api/buyer/connections -H "Authorization: Bearer $B_TOKEN" # no phone
curl -s $BASE/api/buyer/connections/1/contact -H "Authorization: Bearer $B_TOKEN" # 400 until accepted
# farmer accepts
curl -s -X PATCH $BASE/api/farmer/connections/1 -H "Authorization: Bearer $F_TOKEN" -H 'Content-Type: application/json' -d '{"status":"accepted"}'
curl -s $BASE/api/buyer/connections/1/contact -H "Authorization: Bearer $B_TOKEN" # 200 {phone_number: "+94770000901"}
curl -s $BASE/api/farmer/connections/1/contact -H "Authorization: Bearer $F_TOKEN" # buyer primary
curl -s -X PATCH $BASE/api/farmer/connections/1 -H "Authorization: Bearer $F_TOKEN" -H 'Content-Type: application/json' -d '{"status":"completed"}' # seam for future transactions
```

Errors: `401` missing/invalid/expired JWT, `403` role (`farmer role required`/`buyer role required`) or `farmer subscription required`/`expired — please renew` (bypass `AK_MARKETPLACE__SKIP_SUBSCRIPTION_CHECK=1`), `404` not found/hide-owner, `409` `already requested`, `400` invalid transition/terminal, `422` validation.

### Chat (supervisor) marketplace — `tools/marketplace_tools.py:130` (all `@guarded`, `AK_MARKETPLACE__DEV_USER_ID` injection for `demo.py`, WhatsApp `session.id` wa_id fallback via `marketplace/auth.py:25` `normalize_phone`)

Bound to `agents/supervisor.py:29` `LangGraphToolBuilder.bind` (13 tools inc. `get_farmer_context: tools/context_tools.py:16` + `plan_tools` + `_analyze_attachments`). `TRIAGE_INSTRUCTIONS:95` adds: farmer sell (`create_listing_tool`) → confirm ID, farmer `list_my_listings_tool`/`delete_listing_tool`, buyer `browse_listings_tool`/`match_listings_tool` (both `role in {"buyer","farmer"}`, JWT-only), `connect_to_listing_tool` (buyer-only, no phone). `post_model_hook` `agents/supervisor_guardrails.py:47` still sees all tools.

```bash
# Demo CLI with dev injection (no WhatsApp)
AK_MARKETPLACE__DEV_USER_ID=1 python demo.py
# then: "I have 500kg tomatoes at 120/kg to sell" -> create_listing_tool
# "show my listings" -> list_my_listings_tool
# "delete listing 2" -> delete_listing_tool
# buyer: "show me tomato near Kandy" -> browse; "match 200kg tomato Kandy" -> match; "connect to listing 1" -> connect

# REST chat (agent)
curl -s $BASE/api/v1/chat -H 'Content-Type: application/json' -d '{"prompt":"Show me tomato near Kandy","session_id":"buyer-1","agent":"triage"}'

Buyer chat examples (mobile JWT session `agri:user:{buyer_id}`):
- "Find the best 200kg of tomatoes near Kandy" → `match_listings_tool` (health + district ranking)
- "Is listing 12 healthy?" → `listing_insights_tool` (open Crop analytics on Home for the chart)
- "Where is my rider?" → `my_orders_tool` / `order_status_tool` (read-only; place orders in Inbox)
- "Pickup or delivery?" → explains modes; accepted connections → Place order in the app

Rider chat examples (mobile JWT session `agri:user:{rider_id}`):
- "What jobs are nearby?" → `nearby_delivery_jobs_tool` (hint if offline/no GPS/active job)
- "What's my active delivery?" → `rider_active_job_tool`
- "How do I go online?" → explain Jobs tab Online toggle + GPS; accept jobs in app only
- Buyer PIN at drop-off → enter on Deliveries tab, not in chat
```

### Conversation continuity across restarts

Under Docker the same `session_id` survives `docker compose restart app` — sessions, attachments, and case history live in Redis:

```bash
curl -s $BASE/api/v1/chat -H 'Content-Type: application/json' \
  -d '{"prompt":"My location is Kandy. My tomato plants were diagnosed with early blight.","session_id":"farmer-1"}'
docker compose restart app
curl -s $BASE/api/v1/chat -H 'Content-Type: application/json' \
  -d '{"prompt":"It is getting worse. What should I do?","session_id":"farmer-1"}'
# -> reply references tomato / early blight without re-asking
```

## API / WhatsApp

`app.py:10` `load_dotenv(".env.local")` before `agentkernel` imports, then Alembic migrations run at startup (single schema authority). The explicit handler list mounts **both** the agent REST routes (`AgentRESTRequestHandler` → `/api/v1/*`) and the WhatsApp webhook — dropping one silently removes its routes.

1. Fill `AK_WHATSAPP__ACCESS_TOKEN`, `PHONE_NUMBER_ID`, `VERIFY_TOKEN` in `.env.local` (and `AK_WHATSAPP__APP_SECRET` if verifying `X-Hub-Signature-256`).
2. Start: `uv run python app.py` or `docker compose up --build` (health `http://localhost:8000/health`).
3. Expose: `ngrok http 8000`.
4. Meta console → WhatsApp → Configuration: callback `https://<ngrok>/whatsapp/webhook`, verify token, subscribe `messages`.
5. Send to sandbox number — active `farmer` (`users.phone_number` `E.164`, `wa_id` `+` normalized, `role=farmer`, `subscription_status=active`) reaches supervisor; others get `AgriPilot WhatsApp is for active farmer accounts. Sign up at <AK_MARKETPLACE__SIGNUP_URL>.` and **no** LLM call (`whatsapp_handler.py:52`).

## API / Telegram

Same server as REST + WhatsApp (`telegram_handler.py` `GatedTelegramHandler`, subclass of Agent Kernel's `AgentTelegramRequestHandler`). The stock handler already fast-acks (Starlette `BackgroundTasks`) and supports photos/documents/captions for vision; the subclass adds update-ID dedup (`update_id`, `_SEEN_LIMIT=1024`) and the farmer-only hard gate.

1. Create a bot: Telegram → `@BotFather` → `/newbot`; copy the 46-char token into `AK_TELEGRAM__BOT_TOKEN`. Pick any random string for `AK_TELEGRAM__WEBHOOK_SECRET`.
2. Start `uv run python app.py` behind ngrok, then register the webhook once:
   `https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<ngrok>/telegram/webhook&secret_token=<WEBHOOK_SECRET>` — verify with `getWebhookInfo`. Webhook and `getUpdates` polling are mutually exclusive.
3. **Linking:** an unlinked chat gets a contact-share keyboard; tapping it sends the farmer's real phone number, which is E.164-normalized and matched against `users.phone_number`. Only `role=farmer` + `subscription_status=active` accounts link — the chat ID is stored in `users.telegram_chat_id` (nullable unique, migration `b4e8f1a2c7d9`) and every later message is gated on it. Non-farmers/inactive subscriptions get the signup notice, never an LLM call. Forwarded contacts (`contact.user_id != from.id`) are rejected.
4. Sessions key on Telegram `chat_id` — case history is per-channel (not shared with the WhatsApp wa_id session) for now.
5. Rate limits: ~30 msgs/sec globally, ~1/sec per chat — bursts may see Telegram 429s with `retry_after`.

## Tests

Run from this directory (repo-root `pytest` collects monorepo and fails):

```bash
OPENAI_API_KEY=sk-dummy uv run pytest          # dummy key enough (agents/model.py guard)
uv run pytest -m "not slow"                    # skip weight/LLM (default for iteration)
uv run pytest tests/weather_tool_test.py::test_name
OPENAI_API_KEY=sk-dummy uv run pytest tests/whatsapp_fastack_test.py -v  # handler now has _skip_marketplace_gate for dedup tests
OPENAI_API_KEY=sk-dummy uv run pytest tests/telegram_fastack_test.py tests/telegram_gate_test.py -v  # Telegram dedup + gate/linking (AK_TELEGRAM__BOT_TOKEN=dummy set in-file)
```

`conftest.py:91` stubs `tools/weather_tool.py:1` `_http_get` with canned Open-Meteo payloads. Marketplace tests (`marketplace_auth_test.py`, `marketplace_farmer_listings_test.py`) use in-memory SQLite `StaticPool`; `tests/marketplace_postgres_smoke_test.py` and `tests/redis_session_test.py` run against real Postgres/Redis when reachable (`docker compose up -d db redis`) and skip otherwise. `AK_MARKETPLACE__SKIP_SUBSCRIPTION_CHECK=1` bypasses farmer gate where noted. `AK_MARKETPLACE__DEV_USER_ID` seeds chat tools in tests.

## Weather & Knowledge

Weather [Open-Meteo](https://open-meteo.com) — no key, **no signup** (10k/d, 5k/h, 600/m), geocode cached, forecast `AGRIPILOT_WEATHER_CACHE_TTL_MINUTES=60`. After editing `data/knowledge_docs/`: `uv run python scripts/ingest_knowledge.py` (rebuilds `data/chroma_db/`, gitignored).

## Marketplace database

**Postgres-only** since 2026-08-25: driver `psycopg` 3, schema authority is Alembic under `migrations/` (`app.py` startup and `scripts/seed_admin.py` call `marketplace.database.run_migrations()`; never reintroduce `Base.metadata.create_all` as a runtime path). Compose wires `AK_MARKETPLACE__DATABASE_URL` to the `db` service. Tests use per-test in-memory SQLite fixtures — pytest needs no Docker or Postgres. Legacy `data/app.db` is read only by the one-shot `scripts/migrate_sqlite_to_postgres.py`.

## Status

Market specialist removed 2026-08-24 (no reliable API). Durable memory with Redis-backed sessions and attachments, farmer profile/case history, and follow-up resolution — restart continuity verified over REST. Marketplace dual-phone (`contact_phone`) gated reveal `GET .../contact` after `accepted`.

## VPS deployment (production)

Production stack: **Caddy** (automatic HTTPS on 80/443) → **app** (Agent Kernel REST + agent runner) → **Postgres 16** + **Redis 7** on a private Docker network. Only Caddy is public; database and Redis ports are not published.

### Prerequisites

- Ubuntu 22.04 or 24.04 VPS with SSH access
- DNS `A`/`AAAA` record for your domain pointing at the VPS **before** the first deploy (Let's Encrypt validation)
- Firewall: allow inbound **22**, **80**, **443** only
- Meta WhatsApp Cloud API + Telegram bot credentials
- One LLM provider API key

### One-command deploy (fresh VPS)

```bash
export REPO_URL=https://github.com/yaalalabs/agent-kernel.git
export BRANCH=main
export INSTALL_DIR=/opt/agent-kernel

curl -fsSL https://raw.githubusercontent.com/yaalalabs/agent-kernel/main/use-cases/agri-pilot/deploy/deploy-vps.sh \
  | bash -s -- setup   # optional if you prefer copying deploy/.env.production.example manually

# After editing deploy/.env.production on the server:
bash /opt/agent-kernel/use-cases/agri-pilot/deploy/deploy-vps.sh deploy
```

Or clone first, then deploy from the repo:

```bash
git clone --branch main https://github.com/yaalalabs/agent-kernel.git /opt/agent-kernel
cd /opt/agent-kernel/use-cases/agri-pilot
cp deploy/.env.production.example deploy/.env.production
chmod 600 deploy/.env.production
# fill DOMAIN, LLM, WhatsApp, Telegram, and strong secrets
./deploy/deploy-vps.sh deploy
```

First run of `./deploy/deploy-vps.sh setup` generates strong JWT/Postgres/WhatsApp-verify/Telegram-webhook secrets into `deploy/.env.production` (mode `600`). The script **never prints secret values** and **never overwrites** an existing populated env file.

### Update workflow

From the AgriPilot directory on the VPS (after pushing your branch to the remote):

```bash
cd /opt/agent-kernel/use-cases/agri-pilot
git pull --ff-only origin main   # optional — deploy also pulls when the tree is clean
./deploy/deploy-vps.sh update
```

`update` is an alias for `deploy`. The script fast-forwards the configured Git branch (unless `DEPLOY_SKIP_GIT=1`), rebuilds the app image, runs `alembic upgrade head` (including plant-tracking tables), creates the `plant-media` volume if missing, restarts services, and probes `https://<DOMAIN>/health`. Named volumes (Postgres, Redis, Caddy certs, Chroma cache, **plant-media**) are retained across redeploys.

If you copied code to the server without git (rsync/scp), deploy the tree on disk:

```bash
cd /opt/agent-kernel/use-cases/agri-pilot
DEPLOY_SKIP_GIT=1 ./deploy/deploy-vps.sh update
```

After a successful deploy, rebuild the mobile release APK with `--dart-define=API_BASE_URL=https://<DOMAIN>`.

### Operations

| Command | Purpose |
|---------|---------|
| `./deploy/deploy-vps.sh deploy` | Full deploy (build, migrate, start, verify) |
| `./deploy/deploy-vps.sh update` | Same as deploy — recommended on the VPS after pulling changes |
| `./deploy/deploy-vps.sh status` | Container status + public `/health` probe |
| `./deploy/deploy-vps.sh logs [service]` | Follow logs (`db`, `redis`, `app`, `caddy`, …) |
| `./deploy/deploy-vps.sh restart` | Restart app + Caddy |
| `./deploy/deploy-vps.sh backup` | Timestamped Postgres dump under `deploy/backups/` |
| `./deploy/deploy-vps.sh restore <file.sql.gz>` | Destructive DB restore (requires typing `restore`) |
| `./deploy/validate-deploy.sh` | `bash -n`, optional ShellCheck, compose config validation |
| `./deploy/validate-deploy.sh --smoke` | Local build + migration + `/health` without Caddy/LLM calls |

### Webhooks

After a successful deploy the script registers Telegram:

- Webhook URL: `https://<DOMAIN>/telegram/webhook`
- Secret: `AK_TELEGRAM__WEBHOOK_SECRET` from `deploy/.env.production`

WhatsApp Meta console (manual):

- Callback URL: `https://<DOMAIN>/whatsapp/webhook`
- Verify token: `AK_WHATSAPP__VERIFY_TOKEN`
- Subscribe to `messages`

Mobile release builds must use HTTPS — see [`mobile/README.md`](mobile/README.md).

### Files

| Path | Role |
|------|------|
| `deploy/docker-compose.vps.yml` | Production Compose stack |
| `deploy/Caddyfile` | Automatic HTTPS reverse proxy |
| `deploy/Dockerfile` | Hardened app image (non-root, baked knowledge ingest) |
| `deploy/.env.production.example` | Documented env template (no secrets) |
| `deploy/.env.production` | Real production secrets (gitignored, mode `600`) |
| `deploy/deploy-vps.sh` | Idempotent deploy + operations |
| `deploy/backups/` | Postgres dumps (gitignored) |

