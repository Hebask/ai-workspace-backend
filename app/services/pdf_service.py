from __future__ import annotations

import base64
from pathlib import Path
from typing import List, Tuple
from datetime import datetime, timezone

import numpy as np
from pypdf import PdfReader

from app.core.config import settings
from app.services.embeddings_service import EmbeddingsService


def _chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks = []
    i = 0
    n = len(text)
    while i < n:
        j = min(i + chunk_size, n)
        chunk = text[i:j].strip()
        if chunk:
            chunks.append(chunk)
        if j == n:
            break
        i = max(0, j - overlap)
    return chunks


def _cosine(a: List[float], b: List[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    denom = (np.linalg.norm(va) * np.linalg.norm(vb)) + 1e-12
    return float(np.dot(va, vb) / denom)


class PdfService:
    @staticmethod
    def save_pdf_bytes(user_id: str, pdf_bytes: bytes, filename: str) -> str:
        base = Path(settings.storage_dir)
        out_dir = base / "files" / user_id
        out_dir.mkdir(parents=True, exist_ok=True)

        # timestamped filename to avoid collisions
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_name = filename.replace("/", "_").replace("\\", "_")
        path = out_dir / f"{ts}__{safe_name}"
        path.write_bytes(pdf_bytes)
        return str(path)

    @staticmethod
    def read_pdf_text_by_page(pdf_path: str) -> List[Tuple[int, str]]:
        reader = PdfReader(pdf_path)
        pages = []
        for idx, page in enumerate(reader.pages):
            try:
                txt = page.extract_text() or ""
            except Exception:
                txt = ""
            pages.append((idx + 1, txt))
        return pages

    @staticmethod
    async def chunk_and_embed_pages(
        user_id: str,
        file_id: str,
        conversation_id: str | None,
        pages: List[Tuple[int, str]],
    ) -> List[dict]:
        chunks_docs: List[dict] = []
        chunk_size = settings.rag_chunk_size
        overlap = settings.rag_chunk_overlap

        for page_num, page_text in pages:
            chunks = _chunk_text(page_text, chunk_size=chunk_size, overlap=overlap)
            for ci, chunk in enumerate(chunks):
                emb = await EmbeddingsService.embed_text(chunk)
                chunks_docs.append(
                    {
                        "user_id": user_id,
                        "file_id": file_id,
                        "conversation_id": conversation_id,
                        "page": page_num,
                        "chunk_index": ci,
                        "text": chunk,
                        "embedding": emb,
                        "created_at": datetime.now(timezone.utc),
                    }
                )
        return chunks_docs

    @staticmethod
    async def retrieve_top_k(query: str, chunks: List[dict], k: int) -> List[dict]:
        q_emb = await EmbeddingsService.embed_text(query)
        scored = []
        for ch in chunks:
            score = _cosine(q_emb, ch["embedding"])
            scored.append((score, ch))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ch for _, ch in scored[:k]]