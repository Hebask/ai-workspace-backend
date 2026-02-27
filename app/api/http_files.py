from __future__ import annotations
import asyncio
from bson import ObjectId
from app.services.job_service import JobService
from app.services.pdf_ingest_worker import PdfIngestWorker
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from app.api.http_auth import get_current_user
from app.repositories.files_repo import FilesRepo
from app.services.pdf_service import PdfService

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    conversation_id: str | None = Form(default=None),
    user: dict = Depends(get_current_user),
):
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Only PDF supported for now")

    pdf_bytes = await file.read()
    storage_path = PdfService.save_pdf_bytes(user["_id"], pdf_bytes, file.filename)

    file_doc = await FilesRepo.create_file(
        user_id=user["_id"],
        conversation_id=conversation_id,
        filename=file.filename,
        storage_path=storage_path,
        size_bytes=len(pdf_bytes),
        mime=file.content_type or "application/pdf",
    )

    pages = PdfService.read_pdf_text_by_page(storage_path)
    chunk_docs = await PdfService.chunk_and_embed_pages(
        user_id=user["_id"],
        file_id=file_doc["_id"],
        conversation_id=conversation_id,
        pages=pages,
    )
    inserted = await FilesRepo.insert_chunks(chunk_docs)

    return {"file": file_doc, "pages": len(pages), "chunks": inserted}

@router.post("/upload-async")
async def upload_pdf_async(
    file: UploadFile = File(...),
    conversation_id: str | None = Form(default=None),
    user: dict = Depends(get_current_user),
):
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Only PDF supported for now")

    pdf_bytes = await file.read()
    storage_path = PdfService.save_pdf_bytes(user["_id"], pdf_bytes, file.filename)

    file_doc = await FilesRepo.create_file(
        user_id=user["_id"],
        conversation_id=conversation_id,
        filename=file.filename,
        storage_path=storage_path,
        size_bytes=len(pdf_bytes),
        mime=file.content_type or "application/pdf",
    )

    job_id = str(ObjectId())
    JobService.create(
        job_id,
        payload={
            "type": "pdf_ingest",
            "user_id": user["_id"],
            "file_id": file_doc["_id"],
            "conversation_id": conversation_id,
            "filename": file.filename,
            "plan": user.get("plan", "free"),
        },
    )

    # start background task (MVP)
    asyncio.create_task(
        PdfIngestWorker.ingest_pdf_job(
            job_id=job_id,
            user_id=user["_id"],
            file_id=file_doc["_id"],
            storage_path=storage_path,
            conversation_id=conversation_id,
            plan=user.get("plan","free"),
        )
    )

    return {"job_id": job_id, "file": file_doc}

@router.get("/jobs/{job_id}")
async def job_status(job_id: str, user: dict = Depends(get_current_user)):
    from app.services.job_service import JobService

    data = JobService.get(job_id)
    if not data:
        raise HTTPException(status_code=404, detail="Job not found")

    # Basic ownership check: compare user_id if present in payload
    payload = data.get("payload") or {}
    if payload.get("user_id") and payload["user_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    return data