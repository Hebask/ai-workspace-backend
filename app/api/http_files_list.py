from __future__ import annotations
from fastapi import APIRouter, Depends
from app.api.http_auth import get_current_user
from app.repositories.files_repo import FilesRepo

router = APIRouter(prefix="/files", tags=["files"])

@router.get("")
async def list_files(conversation_id: str | None = None, limit: int = 50, user: dict = Depends(get_current_user)):
    files = await FilesRepo.list_files(user["_id"], conversation_id=conversation_id, limit=limit)
    return {"files": files}