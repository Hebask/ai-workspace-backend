from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List
from bson import ObjectId
from app.core.db import get_db


class FilesRepo:
    @staticmethod
    async def ensure_indexes():
        db = get_db()
        await db.files.create_index([("user_id", 1), ("created_at", -1)])
        await db.file_chunks.create_index([("user_id", 1), ("file_id", 1)])
        await db.file_chunks.create_index([("user_id", 1), ("conversation_id", 1)])

    @staticmethod
    async def create_file(
        user_id: str,
        conversation_id: str | None,
        filename: str,
        storage_path: str,
        size_bytes: int,
        mime: str = "application/pdf",
    ) -> dict:
        db = get_db()
        doc = {
            "_id": str(ObjectId()),
            "user_id": user_id,
            "conversation_id": conversation_id,
            "filename": filename,
            "mime": mime,
            "size_bytes": size_bytes,
            "storage_path": storage_path,
            "created_at": datetime.now(timezone.utc),
        }
        await db.files.insert_one(doc)
        return doc

    @staticmethod
    async def get_file(user_id: str, file_id: str) -> Optional[dict]:
        db = get_db()
        return await db.files.find_one({"_id": file_id, "user_id": user_id})

    @staticmethod
    async def list_files(user_id: str, conversation_id: str | None = None, limit: int = 50) -> List[dict]:
        db = get_db()
        q = {"user_id": user_id}
        if conversation_id:
            q["conversation_id"] = conversation_id
        cursor = db.files.find(q).sort("created_at", -1).limit(limit)
        return [doc async for doc in cursor]

    @staticmethod
    async def insert_chunks(chunks: list[dict]) -> int:
        if not chunks:
            return 0
        db = get_db()
        res = await db.file_chunks.insert_many(chunks)
        return len(res.inserted_ids)

    @staticmethod
    async def get_chunks_for_file(user_id: str, file_id: str, limit: int = 2000) -> List[dict]:
        db = get_db()
        cursor = db.file_chunks.find({"user_id": user_id, "file_id": file_id}).limit(limit)
        return [doc async for doc in cursor]