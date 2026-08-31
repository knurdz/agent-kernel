FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

ARG APP_UID=10001
RUN useradd --create-home --uid ${APP_UID} --shell /usr/sbin/nologin agripilot \
    && mkdir -p /app/data/plant_media /app/data/listing_media /home/agripilot/.cache/chroma /home/agripilot/.cache/uv \
    && chown -R agripilot:agripilot /app /home/agripilot

WORKDIR /app
USER agripilot

ENV PATH="/app/.venv/bin:${PATH}" \
    UV_NO_SYNC=1 \
    UV_CACHE_DIR=/home/agripilot/.cache/uv \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=random

COPY --chown=agripilot:agripilot use-cases/agri-pilot/pyproject.toml use-cases/agri-pilot/uv.lock ./
RUN --mount=type=cache,target=/home/agripilot/.cache/uv,uid=10001,gid=10001 \
    uv sync --frozen --no-dev

# PyPI agentkernel 0.8.1 predates auth.authoriser and mobile thread routes — use monorepo ak-py.
# --no-deps keeps uv.lock pins (langgraph-prebuilt==1.0.5) from being upgraded by ak-py extras.
COPY --chown=agripilot:agripilot ak-py /deps/ak-py
RUN --mount=type=cache,target=/home/agripilot/.cache/uv,uid=10001,gid=10001 \
    uv pip install --python .venv/bin/python --reinstall --no-deps \
    -e "/deps/ak-py"

# Bake verified knowledge in its own layer so marketplace/mobile-only deploys skip re-ingest.
COPY --chown=agripilot:agripilot use-cases/agri-pilot/scripts/ingest_knowledge.py scripts/
COPY --chown=agripilot:agripilot use-cases/agri-pilot/data/knowledge_docs data/knowledge_docs
COPY --chown=agripilot:agripilot use-cases/agri-pilot/data/crop_guides data/crop_guides
COPY --chown=agripilot:agripilot \
    use-cases/agri-pilot/tools/__init__.py \
    use-cases/agri-pilot/tools/crop_guide.py \
    tools/
RUN .venv/bin/python scripts/ingest_knowledge.py

COPY --chown=agripilot:agripilot use-cases/agri-pilot /app

# Final app COPY must not drop the baked index (chroma_db is dockerignored in build context).
RUN test -d data/chroma_db && test -n "$(ls -A data/chroma_db)"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["python", "app.py"]
