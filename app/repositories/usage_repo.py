from __future__ import annotations

from datetime import datetime, timezone
from app.core.db import get_db


class UsageRepo:
    @staticmethod
    async def ensure_indexes():
        db = get_db()
        await db.usage_events.create_index([("user_id", 1), ("created_at", -1)])
        await db.usage_events.create_index([("user_id", 1), ("kind", 1), ("created_at", -1)])

    @staticmethod
    async def log_event(user_id: str, kind: str, units: int, meta: dict | None = None):
        db = get_db()
        await db.usage_events.insert_one(
            {
                "user_id": user_id,
                "kind": kind,  # chat | pdf_pages | image
                "units": int(units),
                "meta": meta or {},
                "created_at": datetime.now(timezone.utc),
            }
        )