from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class MessageCreate(BaseModel):
    content: str


class MessagePublic(BaseModel):
    id: str = Field(..., alias="_id")
    conversation_id: str
    user_id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    created_at: datetime
    meta: dict | None = None