# AgriPilot

Agentic AI agricultural assistant for smallholder farmers, built on
[Agent Kernel](https://github.com/yaalalabs) with LangGraph.

See `AgriPilot_Full_Agentic_AI_Workflow.md` for the full architecture, and
`PLAN.md` for the incremental build plan this project follows.

## Setup

```bash
export OPENAI_API_KEY=sk-...
chmod +x build.sh && ./build.sh
source .venv/bin/activate
python demo.py
```

## Tests

```bash
uv run pytest
```

## Local WhatsApp testing (Phase 8)

`app.py` serves the WhatsApp Cloud API webhook and fails fast at startup unless
`AK_WHATSAPP__ACCESS_TOKEN`, `AK_WHATSAPP__PHONE_NUMBER_ID` and a verify token
are set (`config.yaml` holds the default `whatsapp.verify_token`; env vars
override — see `.env.local.example`). The same values are required for
`docker compose up`, since the container runs `app.py`.

1. Fill the WhatsApp variables in `.env.local`.
2. Start the server: `uv run python app.py` or `docker compose up --build`.
3. Expose it publicly: `ngrok http 8000`.
4. In the Meta app console (developers.facebook.com → WhatsApp → Configuration),
   set the callback URL to `https://<ngrok-id>/whatsapp/webhook` with the
   matching verify token, then subscribe to the **messages** field.
5. Send a message to the test/sandbox number; the reply comes from AgriPilot.

## Status

Phase 8 (WhatsApp interface) in progress. See `plan/00-main.md` for the current
phase (the old `PLAN.md` reference above is stale).
