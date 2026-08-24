"""Auth helpers + FastAPI dependencies (Phase 15 / App.md:12)."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from marketplace.database import get_db
from marketplace.models import User

PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")

_bearer_scheme = HTTPBearer(auto_error=False)
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def normalize_phone(phone: str) -> str:
    norm = re.sub(r"[\s\-\(\)]", "", str(phone).strip())
    if not PHONE_RE.match(norm):
        raise ValueError(f"phone_number must be E.164, got {phone!r}")
    return norm


def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


def _get_jwt_secret() -> str:
    env = os.environ.get("AK_MARKETPLACE__JWT_SECRET")
    if env and env.strip():
        return env.strip()
    # fallback: read config.yaml marketplace.jwt_secret
    try:
        import yaml

        with open("config.yaml", "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        sec = (data.get("marketplace") or {}).get("jwt_secret")
        if isinstance(sec, str) and sec.strip():
            return sec.strip()
    except Exception:
        pass
    return "dev-only-jwt-secret-CHANGE-ME-32-chars-minimum-length-1234"


def _get_jwt_expiry_hours() -> int:
    env = os.environ.get("AK_MARKETPLACE__JWT_EXPIRY_HOURS")
    if env and env.strip().isdigit():
        return int(env.strip())
    try:
        import yaml

        with open("config.yaml", "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        v = (data.get("marketplace") or {}).get("jwt_expiry_hours")
        if isinstance(v, int) and v > 0:
            return v
    except Exception:
        pass
    return 24


def create_access_token(user_id: int, role: str, expiry_hours: Optional[int] = None) -> str:
    exp_hours = expiry_hours if expiry_hours is not None else _get_jwt_expiry_hours()
    exp = datetime.now(timezone.utc) + timedelta(hours=exp_hours)
    payload = {"sub": str(user_id), "role": role, "exp": exp}
    return jwt.encode(payload, _get_jwt_secret(), algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _get_jwt_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")
    data = decode_token(credentials.credentials)
    sub = data.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    try:
        uid = int(sub)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc
    user = db.get(User, uid)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    return user


def require_role(*roles: str):
    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"{roles[0]} role required")
        return user

    return _dep


def require_active_subscription(user: User = Depends(get_current_user)) -> User:
    # Dev bypass
    if os.environ.get("AK_MARKETPLACE__SKIP_SUBSCRIPTION_CHECK") == "1":
        return user
    if user.subscription_status != "active":
        detail = "farmer subscription required" if user.role == "farmer" else "subscription required"
        if user.subscription_status == "expired":
            detail = (
                "farmer subscription expired — please renew"
                if user.role == "farmer"
                else "subscription expired — please renew"
            )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
    return user
