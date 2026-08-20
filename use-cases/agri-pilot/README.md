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

## Status

Phase 0 (project scaffolding) in progress. See `PLAN.md` for the current
increment.
