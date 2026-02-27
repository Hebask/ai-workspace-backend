from __future__ import annotations

from typing import List
from app.core.config import settings
from app.services.openai_client import get_openai_client


class EmbeddingsService:
    @staticmethod
    async def embed_text(text: str) -> List[float]:
        client = get_openai_client()
        resp = await client.embeddings.create(
            model=settings.openai_embed_model,
            input=text,
        )
        return resp.data[0].embedding