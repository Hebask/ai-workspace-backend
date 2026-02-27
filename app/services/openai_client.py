from __future__ import annotations

from openai import AsyncOpenAI
from app.core.config import settings

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=float(settings.openai_timeout_sec),
        )
    return _client