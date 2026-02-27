from __future__ import annotations

import secrets
from app.core.redis import get_redis

class PublicLinkService:
    @staticmethod
    def create_image_token(user_id: str, filename: str, ttl_sec: int = 300) -> str:
        token = secrets.token_urlsafe(24)
        r = get_redis()
        r.set(f"public_image:{token}", f"{user_id}:{filename}", ex=ttl_sec)
        return token

    @staticmethod
    def resolve_image_token(token: str) -> tuple[str, str] | None:
        r = get_redis()
        val = r.get(f"public_image:{token}")
        if not val:
            return None
        user_id, filename = val.split(":", 1)
        return user_id, filename