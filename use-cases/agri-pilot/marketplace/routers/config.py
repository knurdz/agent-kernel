"""Public configuration for mobile clients."""

from __future__ import annotations

import os

from fastapi import APIRouter

from marketplace.channels import public_channel_config
from marketplace.schemas import PublicConfigResponse

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/public", response_model=PublicConfigResponse)
def get_public_config():
    cfg = public_channel_config()
    signup = os.environ.get("AK_MARKETPLACE__SIGNUP_URL", "").strip()
    if not signup:
        try:
            import yaml

            with open("config.yaml", "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            signup = str((data.get("marketplace") or {}).get("signup_url") or "")
        except Exception:
            signup = ""
    return PublicConfigResponse(signup_url=signup or None, **cfg)
