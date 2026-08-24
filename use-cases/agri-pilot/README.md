# AgriPilot

Agentic AI agricultural assistant for smallholder farmers, built on
[Agent Kernel](https://github.com/yaalalabs) with LangGraph.

The incremental build plan lives in `plan/` — start with `plan/00-main.md`,
which links one file per phase and tracks current status. `AGENTS.md` covers
conventions for coding agents working in this directory.

## Architecture

A supervisor (`agents/supervisor.py`) routes each farmer message to three
specialists: `vision_agent` (crop-disease diagnosis), `knowledge_agent`
(agricultural RAG over ChromaDB), and `resource_agent` (weather +
irrigation). Price/selling questions get an honest "market prices not
available" reply — the market specialist was removed on 2026-08-24 after
no reliable market-price API could be found. Two code-level backstops wrap
the LLM prompts:
`agents/supervisor_guardrails.py` (handoff-loop detection + narrated-action
correction) and `agents/knowledge_guardrails.py` (no chemical/dosage advice
without an `allow` verdict from `tools/safety_tool.py::validate_treatment`
against `data/safety_rules.json`). Data-fetching tools are wrapped by
`tools/tool_guard.py` with per-session call limits and timeouts.

## Setup

```bash
cp .env.local.example .env.local   # fill in at least one provider key
./build.sh
python demo.py
```

Set `OPENAI_API_KEY`, `GEMINI_API_KEY`, or `OPENROUTER_API_KEY` in `.env.local`
(precedence when several are set: OpenAI, then Gemini, then OpenRouter;
`AGRIPILOT_MODEL_PROVIDER` forces one). See `.env.local.example` for model
overrides, guardrail switches, and debug flags.

## Tests

Run from this directory (running pytest from the repo root fails — it collects
the whole monorepo):

```bash
OPENAI_API_KEY=sk-dummy uv run pytest          # a dummy key is enough
uv run pytest -m "not slow"                    # skip weight-download / live-LLM tests
uv run pytest tests/weather_tool_test.py::<test_name>
```

## Weather data

Weather forecasts come from [Open-Meteo](https://open-meteo.com) — free for
non-commercial use, **no API key or signup required** (10,000 requests/day,
5,000/hour, 600/minute). Place names are resolved via Open-Meteo's geocoding
endpoint and cached for the process lifetime; forecasts are re-served from a
short-TTL cache (`AGRIPILOT_WEATHER_CACHE_TTL_MINUTES`, default 60) to stay
well inside the free-tier limits. On API failure the agent relays an honest
limitation message instead of guessing conditions. Weather data by
Open-Meteo.com. See `plan/Open-Meteo.md` for the integration reference.

## Knowledge base

After editing files in `data/knowledge_docs/`, rebuild ChromaDB:

```bash
uv run python scripts/ingest_knowledge.py
```

## API / WhatsApp

`app.py` serves the Agent Kernel REST API plus the WhatsApp Cloud API webhook,
and fails fast at startup unless `AK_WHATSAPP__ACCESS_TOKEN`,
`AK_WHATSAPP__PHONE_NUMBER_ID` and a verify token are set (`config.yaml` holds
the default `whatsapp.verify_token`; env vars override — see
`.env.local.example`). The same values are required for `docker compose up`,
since the container runs `app.py`.

1. Fill the WhatsApp variables in `.env.local`.
2. Start the server: `uv run python app.py` or `docker compose up --build`.
3. Expose it publicly: `ngrok http 8000`.
4. In the Meta app console (developers.facebook.com → WhatsApp → Configuration),
   set the callback URL to `https://<ngrok-id>/whatsapp/webhook` with the
   matching verify token, then subscribe to the **messages** field.
5. Send a message to the test/sandbox number; the reply comes from AgriPilot.

## Marketplace database

The marketplace (auth, listings, connections) runs on **Postgres only**
(since Phase 18; driver `psycopg` 3). Schema is versioned with Alembic under
`migrations/`; `app.py` applies pending migrations automatically at startup
(equivalent to `uv run python -m alembic upgrade head`). The target URL is
resolved in this order:

1. `AK_MARKETPLACE__DATABASE_URL` env var
2. `config.yaml: marketplace.database_url`
3. default `postgresql+psycopg://agripilot:agripilot@localhost:5432/agripilot`

```bash
# Docker (recommended): brings up a healthy postgres:16 + the app, wired automatically
docker compose up --build

# Bare metal against your own Postgres
AK_MARKETPLACE__DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db \
  uv run python -m alembic upgrade head

# One-shot import of the legacy (Phases 15-17) SQLite data, if data/app.db exists
AK_MARKETPLACE__DATABASE_URL=postgresql+psycopg://agripilot:agripilot@localhost:5432/agripilot \
  uv run python scripts/migrate_sqlite_to_postgres.py   # refuses non-empty target unless --force
```

Tests do not need Postgres or Docker — each test builds its own in-memory
SQLite engine (`tests/marketplace_postgres_smoke_test.py` additionally runs
against real Postgres when reachable, and skips otherwise). Keep
`AK_MARKETPLACE__JWT_SECRET` out of `config.yaml` in any shared deployment;
set it via environment instead.

## Status

Phases 0–9 (except 7), 15–18 are complete. Open: Phase 7 (durable memory)
and Phases 11–13 (hardening incl. human escalation, demo polish). The market
specialist from Phase 6 was removed on 2026-08-24 — no reliable
market-price API exists for the target crops and region. The marketplace DB
moved from SQLite to Postgres-only on 2026-08-25 (Phase 18). Current details:
`plan/00-main.md`.
