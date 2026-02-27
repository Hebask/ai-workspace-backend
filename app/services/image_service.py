from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import base64
import httpx

from app.core.config import settings
from app.services.openai_client import get_openai_client


class ImageService:
    @staticmethod
    def _user_dir(user_id: str) -> Path:
        base = Path(settings.storage_dir)
        out = base / "images" / user_id
        out.mkdir(parents=True, exist_ok=True)
        return out

    @staticmethod
    async def generate_and_save(user_id: str, prompt: str, size: str | None = None) -> dict:
        client = get_openai_client()

        model = settings.openai_image_model
        size = size or settings.openai_image_size

        resp = await client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
        )

        item = resp.data[0]

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}.png"
        path = ImageService._user_dir(user_id) / filename

        # Case A: URL returned
        url = getattr(item, "url", None)
        if url:
            async with httpx.AsyncClient(timeout=60) as http:
                r = await http.get(url)
                r.raise_for_status()
                path.write_bytes(r.content)
            return {"filename": filename, "path": str(path), "size": size, "model": model, "source": "url"}

        # Case B: base64 returned
        b64 = getattr(item, "b64_json", None)
        if b64:
            img_bytes = base64.b64decode(b64)
            path.write_bytes(img_bytes)
            return {"filename": filename, "path": str(path), "size": size, "model": model, "source": "b64"}

        raise RuntimeError("Image generation returned neither url nor b64_json")