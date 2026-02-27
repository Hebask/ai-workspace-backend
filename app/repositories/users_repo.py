from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId

from app.core.db import get_db


class UsersRepo:
    @staticmethod
    async def ensure_indexes():
        db = get_db()
        await db.users.create_index("email", unique=True)

    @staticmethod
    async def get_by_email(email: str) -> Optional[dict]:
        db = get_db()
        return await db.users.find_one({"email": email})

    @staticmethod
    async def get_by_id(user_id: str) -> Optional[dict]:
        db = get_db()
        return await db.users.find_one({"_id": user_id})

    @staticmethod
    async def create(email: str, password_hash: str, plan: str = "free") -> dict:
        db = get_db()
        doc = {
            "_id": str(ObjectId()),
            "email": email,
            "password_hash": password_hash,
            "plan": plan,
            "created_at": datetime.now(timezone.utc),
        }
        await db.users.insert_one(doc)
        return doc