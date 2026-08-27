FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY . .

# Bake verified knowledge into the image so production does not depend on a runtime ingest step.
RUN uv run python scripts/ingest_knowledge.py

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
