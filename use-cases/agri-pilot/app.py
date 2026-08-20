"""Minimal API entry point for AgriPilot.

This currently exposes only a health check for container orchestration.
The full HTTP API (chat endpoint, webhook, etc.) is built out from Phase 12
onward; this file exists early so Docker has something stable to run and
health-check against.
"""

from fastapi import FastAPI

app = FastAPI(title="AgriPilot")


@app.get("/health")
def health():
    return {"status": "ok"}
