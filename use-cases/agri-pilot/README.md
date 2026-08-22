# AgriPilot

Agentic AI agricultural assistant for smallholder farmers, built on
[Agent Kernel](https://github.com/yaalalabs) with LangGraph.

The incremental build plan lives in `plan/` — start with `plan/00-main.md`,
which links one file per phase and tracks current status. `AGENTS.md` covers
conventions for coding agents working in this directory.

## Architecture

A supervisor (`agents/supervisor.py`) routes each farmer message to four
specialists: `vision_agent` (crop-disease diagnosis), `knowledge_agent`
(agricultural RAG over ChromaDB), `resource_agent` (weather + irrigation), and
`market_agent` (crop prices). Two code-level backstops wrap the LLM prompts:
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
uv run pytest tests/market_tool_test.py::<test_name>
```

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

## Status

Phases 0–6, 8 and 9 are complete. Open: Phase 7 (durable memory) and
Phases 11–13 (real weather/market APIs, hardening incl. human escalation,
demo polish). Current details: `plan/00-main.md`.
