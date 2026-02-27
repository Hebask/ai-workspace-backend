from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from app.api.http_auth import get_current_user
from app.repositories.chat_repo import ChatRepo

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(limit: int = 50, user: dict = Depends(get_current_user)):
    convs = await ChatRepo.list_conversations(user["_id"], limit=limit)
    return {"conversations": convs}


@router.get("/{conversation_id}/messages")
async def get_messages(conversation_id: str, limit: int = 50, user: dict = Depends(get_current_user)):
    msgs = await ChatRepo.get_messages(user["_id"], conversation_id, limit=limit)
    return {"messages": msgs}