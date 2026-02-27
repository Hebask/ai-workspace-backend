from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import bcrypt

from jose import jwt
from app.core.config import settings

def is_refresh_token(payload: dict) -> bool:
    return payload.get("type") == "refresh"

def hash_password(password: str) -> str:
    pw = password.encode("utf-8")
    if len(pw) > 72:
        raise ValueError("Password too long (bcrypt max is 72 bytes).")
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_token(payload: dict[str, Any], expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    to_encode = dict(payload)
    to_encode.update({"iat": int(now.timestamp()), "exp": now + expires_delta})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_alg)


def create_access_token(user_id: str, email: str) -> str:
    return create_token(
        {"sub": user_id, "email": email, "type": "access"},
        timedelta(minutes=settings.access_token_minutes),
    )


def create_refresh_token(user_id: str, email: str) -> str:
    return create_token(
        {"sub": user_id, "email": email, "type": "refresh"},
        timedelta(days=settings.refresh_token_days),
    )


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])