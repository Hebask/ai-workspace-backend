from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId

from app.core.db import get_db


class ChatRepo:
    # ---------- indexes ----------
    @staticmethod
    async def ensure_indexes():
        db = get_db()
        await db.conversations.create_index([("user_id", 1), ("last_message_at", -1)])
        await db.messages.create_index([("conversation_id", 1), ("created_at", 1)])
        await db.messages.create_index([("user_id", 1), ("created_at", -1)])

    # ---------- conversations ----------
    @staticmethod
    async def create_conversation(user_id: str, title: str | None = None) -> dict:
        db = get_db()
        now = datetime.now(timezone.utc)
        doc = {
            "_id": str(ObjectId()),          # store as STRING (consistent)
            "user_id": str(user_id),
            "title": title or "New chat",
            "created_at": now,
            "last_message_at": now,
        }
        await db.conversations.insert_one(doc)
        return doc

    @staticmethod
    async def get_conversation(user_id: str, conversation_id: str) -> Optional[dict]:
        db = get_db()
        return await db.conversations.find_one({"_id": str(conversation_id), "user_id": str(user_id)})

    @staticmethod
    async def ensure_conversation(user_id: str, conversation_id: str | None, title: str = "New chat") -> Optional[dict]:
        if not conversation_id:
            return await ChatRepo.create_conversation(user_id, title=title)

        conv = await ChatRepo.get_conversation(user_id, conversation_id)
        return conv

    @staticmethod
    async def list_conversations(user_id: str, limit: int = 50):
        db = get_db()
        cur = db.conversations.find({"user_id": str(user_id)}).sort("last_message_at", -1).limit(limit)
        out = []
        async for c in cur:
            # _id is already string, but keep it safe
            c["_id"] = str(c["_id"])
            out.append(c)
        return out

    @staticmethod
    async def touch_conversation(user_id: str, conversation_id: str):
        db = get_db()
        await db.conversations.update_one(
            {"_id": str(conversation_id), "user_id": str(user_id)},
            {"$set": {"last_message_at": datetime.now(timezone.utc)}},
        )

    # ---------- messages ----------
    @staticmethod
    async def add_message(
        user_id: str,
        conversation_id: str,
        role: str,
        content: str,
        meta: dict | None = None,
    ) -> dict:
        db = get_db()
        doc = {
            "_id": str(ObjectId()),
            "user_id": str(user_id),
            "conversation_id": str(conversation_id),
            "role": role,
            "content": content,
            "meta": meta,
            "created_at": datetime.now(timezone.utc),
        }
        await db.messages.insert_one(doc)
        await ChatRepo.touch_conversation(user_id, conversation_id)
        return doc

    @staticmethod
    async def get_messages(user_id: str, conversation_id: str, limit: int = 50):
        db = get_db()
        cur = (
            db.messages.find({"user_id": str(user_id), "conversation_id": str(conversation_id)})
            .sort("created_at", 1)
            .limit(limit)
        )
        out = []
        async for m in cur:
            m["_id"] = str(m["_id"])
            out.append(m)
        return out