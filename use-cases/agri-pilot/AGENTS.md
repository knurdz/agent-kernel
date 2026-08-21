# AGENTS.md — AgriPilot

Guidance for AI coding agents working on the AgriPilot use-case (`use-cases/agri-pilot/`).

## Scope

- Work **only** inside `use-cases/agri-pilot/`. The rest of the agent-kernel monorepo
  (`ak-py/`, `examples/`, `e2e/`, `ak-deployment/`, root docs) is out of scope for this
  project; do not analyze or edit it. The root `/AGENTS.md` targets Agent Kernel core
  contributors, not this project.
- The canonical build plan lives in `plan/`: read `plan/00-main.md` first, then only the
  file for the phase you are working on. Mark tasks `[x]` only after their test passes;
  mark blocked items `(blocked: reason)`. Phases 0–3 are complete; Phase 4 (safety &
  guardrails) is in progress.
- `README.md` is stale (references nonexistent files and old status). Trust `plan/`.
- The workflow follows the bundled skills in `.claude/commands/` (`ak-init`, `ak-build`,
  `ak-add-capabilities`, `ak-add-integration`, `ak-test`, `ak-cloud-deploy`).

## Commands

Run everything from this directory (`use-cases/agri-pilot/`). Running pytest from the
repo root fails: it collects the whole monorepo, hits missing optional deps and module
name clashes between examples.

```bash
./build.sh                      # setup: uv venv && uv sync
uv run pytest                   # all tests
uv run pytest -m "not slow"     # skip model-weight-download / real-LLM tests
OPENAI_API_KEY=sk-dummy uv run pytest   # dummy key is enough for unit tests
python demo.py                  # CLI entry point
uv run python scripts/ingest_knowledge.py   # rebuild ChromaDB after editing data/knowledge_docs/
```

- Tests need `OPENAI_API_KEY` or `GEMINI_API_KEY` set (a dummy value works): importing
  `demo` registers agents and `agents/model.py` raises at import time otherwise.
- pytest config is in `pyproject.toml` (`pythonpath = ["."]`, registered `slow` marker);
  use the project venv's pytest — there is no system-wide one.

## Environment & configuration

- `demo.py` calls `load_dotenv(".env.local")` **before** importing agentkernel/agents —
  keep that import order when touching entrypoints. Copy `.env.local.example` to
  `.env.local` for keys.
- `AKConfig` reads `config.yaml` from the CWD at first access (lazy singleton).
- Any config value can be overridden by env vars with prefix `AK_` and `__` nesting;
  they take priority over `config.yaml`. E.g. set
  `AK_GUARDRAIL__INPUT__ENABLED=false` / `AK_GUARDRAIL__OUTPUT__ENABLED=false` to turn
  guardrails off with zero API cost while testing.
- Provider/model selection env vars: `AGRIPILOT_MODEL_PROVIDER`, `AGRIPILOT_OPENAI_MODEL`,
  `AGRIPILOT_GEMINI_MODEL` (see `agents/model.py`; OpenAI preferred if both keys set).

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

`agentkernel[...]` is installed into `.venv` from PyPI (pinned in `pyproject.toml` /
`uv.lock`) — it is **not** an editable link to `../../ak-py/src`. Editing Agent Kernel
core source has no effect on this project; upgrade via `uv lock && uv sync`.

## Codebase map

- `demo.py` — CLI entry point; registers `LangGraphModule([triage_agent])`.
- `app.py` — FastAPI entry point, health check only until Phase 12.
- `agents/supervisor.py` — LangGraph supervisor routing to specialist agents
  (`vision_agent`, `knowledge_agent`); `agents/supervisor_guardrails.py` adds a
  `post_model_hook` backstop against narrated-but-not-executed handoffs.
- `tools/` — agent tools (vision, knowledge RAG, farmer context, safety validation).
- `state/farmer_context.py` — per-session farmer state tool.
- `data/` — knowledge docs (header + `===` + body format), `safety_rules.json`,
  `data/chroma_db/` (generated; rebuild via `scripts/ingest_knowledge.py`).

## Style

black + isort with `line-length = 120` in this project's `pyproject.toml` (note: the
Agent Kernel core repo uses 150 — do not apply that here).
