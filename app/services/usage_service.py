from __future__ import annotations

from datetime import datetime, timezone
from app.core.redis import get_redis
from app.core.config import settings


def _day_key() -> str:
    # UTC day bucket
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class UsageService:
    @staticmethod
    def _key(user_id: str, kind: str) -> str:
        return f"usage:{_day_key()}:{user_id}:{kind}"

    @staticmethod
    def limits_for_plan(plan: str) -> dict:
        if (plan or "free").lower() == "pro":
            return {
                "chat": settings.pro_chat_per_day,
                "pdf_pages": settings.pro_pdf_pages_per_day,
                "image": settings.pro_image_per_day,
            }
        return {
            "chat": settings.free_chat_per_day,
            "pdf_pages": settings.free_pdf_pages_per_day,
            "image": settings.free_image_per_day,
        }

    @staticmethod
    def add_and_check(user_id: str, plan: str, kind: str, units: int) -> tuple[bool, int, int]:
        """
        returns: (allowed, used_after, limit)
        """
        r = get_redis()
        limits = UsageService.limits_for_plan(plan)
        if kind not in limits:
            # unknown kind -> block by default
            return False, 0, 0

        key = UsageService._key(user_id, kind)
        limit = int(limits[kind])

        used_after = int(r.incrby(key, int(units)))
        # expire roughly end-of-day (simple 24h)
        r.expire(key, 60 * 60 * 24)

        return used_after <= limit, used_after, limit