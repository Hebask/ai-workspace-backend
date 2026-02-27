from __future__ import annotations

from typing import AsyncIterator, List, Dict, Any

from app.core.config import settings
from app.services.openai_client import get_openai_client


class ChatService:
    @staticmethod
    async def stream_reply(messages: List[Dict[str, Any]]) -> AsyncIterator[str]:
        """
        messages format example:
        [
          {"role":"system","content":"..."},
          {"role":"user","content":"hello"}
        ]
        """
        if not settings.openai_api_key:
            yield "OPENAI_API_KEY is not set."
            return

        client = get_openai_client()

        stream = await client.responses.create(
            model=settings.openai_model,
            input=messages,
            stream=True,
        )

        async for event in stream:
            etype = getattr(event, "type", None)

            if etype == "response.output_text.delta":
                delta = getattr(event, "delta", None)
                if delta:
                    yield delta

            elif etype == "error":
                err = getattr(event, "error", None) or getattr(event, "message", None) or str(event)
                yield f"\n[Error] {err}"
                return