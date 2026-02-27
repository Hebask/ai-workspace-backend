from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from app.services.public_link_service import PublicLinkService
from app.api.http_auth import get_current_user
from app.core.config import settings

router = APIRouter(prefix="/images", tags=["images"])


@router.get("/{user_id}/{filename}")
async def get_image(user_id: str, filename: str, user: dict = Depends(get_current_user)):
    # Only allow users to access their own images (simple MVP)
    if user_id != user["_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    path = Path(settings.storage_dir) / "images" / user_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(str(path), media_type="image/png", filename=filename)

@router.get("/public/{token}")
async def public_image(token: str):
    resolved = PublicLinkService.resolve_image_token(token)
    if not resolved:
        raise HTTPException(status_code=404, detail="Not found or expired")

    user_id, filename = resolved
    path = Path(settings.storage_dir) / "images" / user_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(str(path), media_type="image/png", filename=filename)