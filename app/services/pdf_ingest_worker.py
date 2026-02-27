from __future__ import annotations

import asyncio
from typing import Optional
from app.services.usage_service import UsageService
from app.repositories.usage_repo import UsageRepo
from app.repositories.files_repo import FilesRepo
from app.services.pdf_service import PdfService
from app.services.job_service import JobService


class PdfIngestWorker:
    @staticmethod
    async def ingest_pdf_job(job_id, user_id, plan, file_id, storage_path, conversation_id):
        """
        Background job:
        - Extract PDF text
        - Chunk + embed
        - Store chunks in Mongo
        - Update Redis job status/progress
        """
        try:
            JobService.update(job_id, status="running", stage="extract_text", progress=0)

            pages = PdfService.read_pdf_text_by_page(storage_path)
            total_pages = len(pages) or 1
            JobService.update(job_id, total=total_pages)

            if JobService.is_cancel_requested(job_id):
                JobService.update(job_id, status="cancelled", stage="cancelled_before_embedding")
                return

            JobService.update(job_id, stage="chunk_embed", progress=0)

            # Embed page-by-page so we can report progress and allow cancellation
            all_chunk_docs = []
            inserted_total = 0

            for idx, (page_num, page_text) in enumerate(pages, start=1):
                if JobService.is_cancel_requested(job_id):
                    JobService.update(job_id, status="cancelled", stage="cancelled_during_embedding", result={"chunks_inserted": inserted_total})
                    return
                
                allowed, used, limit = UsageService.add_and_check(user_id, "free", "pdf_pages", 1)
                
                chunk_docs = await PdfService.chunk_and_embed_pages(
                    user_id=user_id,
                    file_id=file_id,
                    conversation_id=conversation_id,
                    pages=[(page_num, page_text)],
                )

                # insert in batches (page by page)
                inserted = await FilesRepo.insert_chunks(chunk_docs)
                inserted_total += inserted

                JobService.update(
                    job_id,
                    stage="chunk_embed",
                    progress=idx,
                    total=total_pages,
                    result={"chunks_inserted": inserted_total},
                )
                allowed, used, limit = UsageService.add_and_check(user_id, plan, "pdf_pages", 1)
                if not allowed:
                    JobService.update(job_id, status="error", stage="quota_exceeded", error=f"PDF page quota exceeded (used={used}, limit={limit}).")
                    return

                await UsageRepo.log_event(user_id, "pdf_pages", 1, meta={"source": "ingest_job", "file_id": file_id, "page": page_num})

            JobService.update(job_id, status="done", stage="done", result={"chunks_inserted": inserted_total, "pages": total_pages})

        except Exception as e:
            JobService.update(job_id, status="error", stage="error", error=f"{type(e).__name__}: {e}")