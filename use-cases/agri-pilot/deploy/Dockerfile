FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY use-cases/agri-pilot/pyproject.toml use-cases/agri-pilot/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# PyPI agentkernel 0.8.1 predates auth.authoriser and mobile thread routes — use monorepo ak-py.
# --no-deps keeps uv.lock pins (langgraph-prebuilt==1.0.5) from being upgraded by ak-py extras.
COPY ak-py /deps/ak-py
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python .venv/bin/python --reinstall --no-deps \
    -e "/deps/ak-py"

COPY use-cases/agri-pilot /app

# Bake verified knowledge into the image so production does not depend on a runtime ingest step.
RUN .venv/bin/python scripts/ingest_knowledge.py

ENV PATH="/app/.venv/bin:${PATH}" \
    UV_NO_SYNC=1 \
    UV_CACHE_DIR=/home/agripilot/.cache/uv \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=random

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin agripilot \
    && mkdir -p /home/agripilot/.cache/chroma /home/agripilot/.cache/uv \
    && chown -R agripilot:agripilot /app /home/agripilot

USER agripilot

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["python", "app.py"]
