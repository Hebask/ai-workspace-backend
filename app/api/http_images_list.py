from __future__ import annotations
from fastapi import APIRouter, Depends
from pathlib import Path
from app.api.http_auth import get_current_user
from app.core.config import settings

router = APIRouter(prefix="/images", tags=["images"])

@router.get("")
async def list_images(user: dict = Depends(get_current_user)):
    d = Path(settings.storage_dir) / "images" / user["_id"]
    if not d.exists():
        return {"images": []}
    imgs = []
    for p in sorted(d.glob("*.png"), reverse=True):
        imgs.append({"filename": p.name, "url": f"{settings.public_base_url}/images/{user['_id']}/{p.name}"})
    return {"images": imgs}