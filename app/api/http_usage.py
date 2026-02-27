from __future__ import annotations

from fastapi import APIRouter, Depends
from app.api.http_auth import get_current_user
from app.services.usage_service import UsageService

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/today")
async def usage_today(user: dict = Depends(get_current_user)):
    plan = user.get("plan", "free")
    limits = UsageService.limits_for_plan(plan)

    used_chat = UsageService.get_used(user["_id"], "chat")
    used_pdf = UsageService.get_used(user["_id"], "pdf_pages")
    used_img = UsageService.get_used(user["_id"], "image")

    return {
        "plan": plan,
        "used": {"chat": used_chat, "pdf_pages": used_pdf, "image": used_img},
        "limits": limits,
        "remaining": {
            "chat": max(limits["chat"] - used_chat, 0),
            "pdf_pages": max(limits["pdf_pages"] - used_pdf, 0),
            "image": max(limits["image"] - used_img, 0),
        },
    }