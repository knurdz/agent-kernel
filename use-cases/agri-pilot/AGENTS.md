# AGENTS.md — AgriPilot

Guidance for AI coding agents working on the AgriPilot use-case (`use-cases/agri-pilot/`).

## Scope

- Work **only** inside `use-cases/agri-pilot/`. The rest of the agent-kernel monorepo
  (`ak-py/`, `examples/`, `e2e/`, `ak-deployment/`, root docs) is out of scope for this
  project; do not analyze or edit it. The root `/AGENTS.md` targets Agent Kernel core
  contributors, not this project.
- **Always consider the ak- skills** under `.agents/skills/` (mirrored in
  `.claude/commands/`) whenever the user asks for anything: load the matching skill
  (`ak-build`, `ak-add-capabilities`, `ak-add-integration`, `ak-test`,
  `ak-cloud-deploy`, `ak-init`) before improvising wiring or workflow steps.
- `README.md` tracks setup, endpoints, and current status; keep it in sync when
  architecture changes.

## Commands

Run everything from this directory (`use-cases/agri-pilot/`). Running pytest from the
repo root fails: it collects the whole monorepo, hits missing optional deps and module
name clashes between examples.

```bash
./build.sh                      # setup: uv venv && uv sync
uv run pytest                   # all tests
uv run pytest -m "not slow"     # skip weight-download / live-LLM tests (default for iteration)
OPENAI_API_KEY=sk-dummy uv run pytest   # dummy key is enough for unit tests
python demo.py                  # CLI entry point
uv run python scripts/ingest_knowledge.py   # rebuild ChromaDB after editing data/knowledge_docs/
```

- Tests need `OPENAI_API_KEY`, `GEMINI_API_KEY`, or `OPENROUTER_API_KEY` set (a dummy
  value works): importing `demo` registers agents and `agents/model.py` raises at import
  time otherwise.
- Single file/test: `uv run pytest tests/weather_tool_test.py::<test_name>` (pytest config
  lives in `pyproject.toml`: `pythonpath = ["."]`, registered `slow` marker). Use the
  project venv's pytest — there is no system-wide one.

## Environment & configuration

- `demo.py` calls `load_dotenv(".env.local")` **before** importing agentkernel/agents —
  keep that import order when touching entrypoints. Copy `.env.local.example` to
  `.env.local` for keys.
- Provider precedence when several keys are set: OpenAI, then Gemini, then OpenRouter,
  unless `AGRIPILOT_MODEL_PROVIDER=openai|gemini|openrouter` forces one. Per-provider
  model overrides: `AGRIPILOT_OPENAI_MODEL`, `AGRIPILOT_GEMINI_MODEL`,
  `AGRIPILOT_OPENROUTER_MODEL` (default `openrouter/free`; see `agents/model.py`).
- `AKConfig` reads `config.yaml` from the CWD at first access (lazy singleton).
- Any config value can be overridden by env vars with prefix `AK_` and `__` nesting;
  they take priority over `config.yaml`. E.g. set
  `AK_GUARDRAIL__INPUT__ENABLED=false` / `AK_GUARDRAIL__OUTPUT__ENABLED=false` to turn
  guardrails off with zero API cost while testing.

## OpenAI guardrails schema gotcha

`guardrails_input.json` / `guardrails_output.json` are **not** free-form lists. They must
match the `openai-guardrails` `PipelineBundles` schema:

```json
{"input": {"guardrails": [{"name": "<RegistryName>", "config": {...}}]}}
```

- Stage keys: `pre_flight`, `input`, `output` (root must be an object with ≥1 stage).
- `name` must be a registry name exactly as registered (`Moderation`, `Jailbreak`, ... —
  capital first letter). Inspect valid names/fields via
  `[s.name for s in default_spec_registry.get_all()]`.
- Config fields are strict (`extra="forbid"`): Moderation takes `categories`
  (e.g. `"violence"`, `"self-harm"` — **not** `content_type`/`threshold`);
  Jailbreak requires `model`. A wrong field fails client init at startup with a pydantic
  error logged under `ak.guardrail.openai`.

## Dependency boundary

- `agentkernel[...]` is installed into `.venv` from PyPI (pinned in `pyproject.toml` /
  `uv.lock`) — it is **not** an editable link to `../../ak-py/src`. Editing Agent Kernel
  core source has no effect on this project; upgrade via `uv lock && uv sync`.
- `langgraph-prebuilt` is pinned to exactly `1.0.5`: `>=1.0.6` imports
  `ExecutionInfo`/`ServerInfo` from `langgraph.runtime`, which `langgraph` 1.0.10 does
  not provide. Don't bump it without checking that import path still resolves.

## Codebase map

- `demo.py` — CLI entry point; registers `LangGraphModule([triage_agent])`.
- `app.py` — FastAPI entry point.
- `agents/supervisor.py` — langgraph_supervisor triage agent routing to three specialists:
  `vision_agent`, `knowledge_agent`, `resource_agent`. Triage rules live
  in its `TRIAGE_INSTRUCTIONS` prompt, including vision→knowledge chaining within one turn.
  Price/selling questions get an honest "no market data" reply — the market
  specialist was removed on 2026-08-24 (no reliable API).
- Two code-level backstops wrap the LLM prompts (prompts alone can't guarantee safety):
  - `agents/supervisor_guardrails.py` — combined `post_model_hook` on the supervisor:
    handoff-loop detection (Increment 7.4) plus narrated-action correction via an
    LLM judge (`build_narration_judge`, meaning-based, any language — replaced an
    earlier phrase regex). Judge model is provider-flexible via
    `AGRIPILOT_JUDGE_PROVIDER` / `AGRIPILOT_JUDGE_MODEL`; judge failures fail open.
  - `agents/knowledge_guardrails.py` — `post_model_hook` on the knowledge agent: a final
    reply naming a chemical + dosage without an `allow` verdict from `validate_treatment`
    triggers one corrective re-invocation (fail-closed, single retry, not a loop).
- `tools/` — agent tools: vision, knowledge RAG, weather, farmer context, safety
  validation (`validate_treatment` against `data/safety_rules.json`). Also:
  - `tools/tool_guard.py` — every data-fetching tool is wrapped in `guarded`: per-session
    call limits (`AGRIPILOT_TOOL_MAX_CALLS`, default 8) and timeouts
    (`AGRIPILOT_TOOL_TIMEOUT_SECONDS`, default 180 s). Debug switches:
    `AGRIPILOT_DEBUG_FORCE_TOOL_FAILURE=<tool names>`,
    `AGRIPILOT_DEBUG_TOOL_DELAY_SECONDS=<float>` for repeatable failure/latency tests.
  - `tools/plan_tools.py` + `state/plan.py` — session-scoped multi-step plan so the
    supervisor can resume interrupted flows; supervisor registers these tools.
  - `tools/attachment_tool.py` — resolves multimodal attachment IDs to local paths
    (used by the vision agent).
- `state/farmer_context.py` — per-session farmer state tool.
- `state/farmer_profile.py` + `tools/profile_tools.py` — durable
  case history per session: `record_case_outcome` appends/updates a
  `CaseRecord` (crop, disease, severity, advice_summary, date,
  follow_up_status open|resolved); the vision agent records diagnoses, the
  knowledge agent records validated advice summaries. Un-guarded on purpose
  (local session state, not external fetches). Triage Step 2b resolves
  "it"/"getting worse" against this profile; knowledge builds on a case's
  recorded advice.
- Durable memory: config.yaml keeps in-memory session +
  attachment stores for bare-metal dev and pytest; docker-compose activates
  Redis via `AK_SESSION__TYPE/AK_SESSION__REDIS__URL` and
  `AK_MULTIMODAL__STORAGE_TYPE/AK_MULTIMODAL__REDIS__URL` on the compose
  `redis` service. `tests/redis_session_test.py` runs against real Redis at
  localhost:6379 (`docker compose up -d redis`), skips otherwise.
- `data/` — knowledge docs (header + `===` + body format), `safety_rules.json`,
  `data/chroma_db/` (generated; rebuild via `scripts/ingest_knowledge.py`).
- `marketplace/` + `migrations/` — marketplace DB. **Postgres-only
   since 2026-08-25**, driver psycopg 3; SQLite exists only as the
  per-test in-memory fixture engines. Schema authority is Alembic:
  `app.py` startup and `scripts/seed_admin.py` call
  `marketplace.database.run_migrations()` (`= alembic upgrade head`); never
  reintroduce `Base.metadata.create_all` as a runtime schema path. Target URL
  precedence: `AK_MARKETPLACE__DATABASE_URL` > `config.yaml` >
  `postgresql+psycopg://agripilot:agripilot@localhost:5432/agripilot`. Tests
  need no Postgres or Docker; `tests/marketplace_postgres_smoke_test.py`
  runs against real Postgres when reachable, skips otherwise. Legacy
  `data/app.db` is read only by `scripts/migrate_sqlite_to_postgres.py`
  (manual, refuses non-empty target unless `--force`).

## Style

black + isort with `line-length = 120` in this project's `pyproject.toml` (note: the
Agent Kernel core repo uses 150 — do not apply that here).
