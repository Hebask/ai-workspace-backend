from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    title: str | None = None


class ConversationPublic(BaseModel):
    id: str = Field(..., alias="_id")
    user_id: str
    title: str
    created_at: datetime
    last_message_at: datetime | None = None