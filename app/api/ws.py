from __future__ import annotations

from app.core.config import settings
from app.repositories.files_repo import FilesRepo
from app.services.pdf_service import PdfService
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import asyncio
from datetime import datetime, timezone
from bson import ObjectId
import base64
from app.core.security import decode_token
from app.repositories.chat_repo import ChatRepo
from app.services.chat_service import ChatService
from app.services.usage_service import UsageService
from app.repositories.usage_repo import UsageRepo
from app.services.image_service import ImageService
from app.tools.mcp_client import MCPClient
import re

router = APIRouter(tags=["ws"])


def _json(obj) -> str:
    def default(o):
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, ObjectId):
            return str(o)
        return str(o)

    return json.dumps(obj, ensure_ascii=False, default=default)


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()

    user = None
    running_jobs: dict[str, asyncio.Task] = {}

    await ws.send_text(_json({"type": "hello", "message": "WS connected. Send {action:'auth', token:'...'}"}))

    async def send(obj: dict):
        await ws.send_text(_json(obj))

    async def handle_chat(job_id: str, conversation_id: str | None, message: str):
        try:
            await send({"type": "started", "action": "chat", "job_id": job_id})

            allowed, used, limit = UsageService.add_and_check(user["_id"], user.get("plan", "free"), "chat", 1)
            if not allowed:
                await send({"type": "error", "error": "Quota exceeded", "kind": "chat", "used": used, "limit": limit, "job_id": job_id})
                return
            await UsageRepo.log_event(user["_id"], "chat", 1, meta={"source": "ws_chat"})

            conv = await ChatRepo.ensure_conversation(user["_id"], conversation_id, title="New chat")
            if not conv:
                await send({"type": "error", "job_id": job_id, "error": "Conversation not found"})
                return
            conversation_id_local = conv["_id"]
            await send({"type": "conversation", "job_id": job_id, "conversation_id": conversation_id_local})

            await ChatRepo.add_message(
                user_id=user["_id"],
                conversation_id=conversation_id_local,
                role="user",
                content=message,
            )
            await ChatRepo.touch_conversation(user["_id"], conversation_id_local)

            history = await ChatRepo.get_messages(user["_id"], conversation_id_local, limit=50)
            openai_input = [{"role": "system", "content": "You are a helpful assistant."}]
            for m in history:
                role = m.get("role", "user")
                if role not in ("user", "assistant", "system"):
                    role = "user"
                openai_input.append({"role": role, "content": m.get("content", "")})

            full = ""
            async for delta in ChatService.stream_reply(openai_input):
                full += delta
                await send({"type": "delta", "job_id": job_id, "delta": delta})

            await ChatRepo.add_message(
                user_id=user["_id"],
                conversation_id=conversation_id_local,
                role="assistant",
                content=full,
                meta={"provider": "openai", "model": settings.openai_model},
            )
            await ChatRepo.touch_conversation(user["_id"], conversation_id_local)

            await send(
                {
                    "type": "result",
                    "action": "chat",
                    "job_id": job_id,
                    "conversation_id": conversation_id_local,
                    "message": full,
                }
            )

        except asyncio.CancelledError:
            await send({"type": "cancelled", "job_id": job_id})
            raise
        except Exception as e:
            await send({"type": "error", "job_id": job_id, "error": f"{type(e).__name__}: {e}"})

    try:
        while True:
            raw = await ws.receive_text()

            try:
                data = json.loads(raw)
            except Exception:
                await send({"type": "error", "error": "Invalid JSON"})
                continue

            try:
                action = data.get("action")

                if action == "auth":
                    token = (data.get("token") or "").strip()
                    if not token:
                        await send({"type": "error", "error": "Missing token"})
                        continue

                    if token.startswith("Bearer "):
                        token = token.split(" ", 1)[1].strip()

                    payload = decode_token(token)
                    if payload.get("type") != "access":
                        await send({"type": "error", "error": "Invalid token type"})
                        continue

                    user = {"_id": payload["sub"], "email": payload.get("email"), "plan": payload.get("plan", "free")}
                    await send({"type": "authed", "user": user})
                    continue

                if not user:
                    await send({"type": "error", "error": "Not authenticated. Send {action:'auth', token:'...'} first."})
                    continue

                # -------------------------
                # ASSISTANT (lightweight router)
                # -------------------------
                if action == "assistant":
                    job_id = data.get("job_id") or f"job_{id(ws)}"
                    message = (data.get("message") or "").strip()
                    conversation_id = data.get("conversation_id")

                    if not message:
                        await send({"type": "error", "job_id": job_id, "error": "Missing message"})
                        continue

                    await send({"type": "started", "action": "assistant", "job_id": job_id})

                    allowed, used, limit = UsageService.add_and_check(user["_id"], user.get("plan", "free"), "chat", 1)
                    if not allowed:
                        await send({"type": "error", "error": "Quota exceeded", "kind": "chat", "used": used, "limit": limit, "job_id": job_id})
                        continue
                    await UsageRepo.log_event(user["_id"], "chat", 1, meta={"source": "ws_assistant"})

                    conv = await ChatRepo.ensure_conversation(user["_id"], conversation_id, title="New chat")
                    if not conv:
                        await send({"type": "error", "job_id": job_id, "error": "Conversation not found"})
                        continue
                    conversation_id_local = conv["_id"]

                    await ChatRepo.add_message(
                        user_id=user["_id"],
                        conversation_id=conversation_id_local,
                        role="user",
                        content=message,
                        meta={"kind": "assistant"},
                    )
                    await ChatRepo.touch_conversation(user["_id"], conversation_id_local)

                    msg_l = message.lower()
                    artifacts: list[dict] = []
                    final_text = ""

                    wants_image = any(k in msg_l for k in ["generate an image", "create an image", "/image", "image of", "draw "])
                    if wants_image:
                        prompt = re.sub(r"^/image\s+", "", message, flags=re.IGNORECASE).strip() or message
                        await send({"type": "progress", "action": "assistant", "job_id": job_id, "stage": "image_generate"})
                        image_doc = await ImageService.generate_and_save(user_id=user["_id"], prompt=prompt, size=settings.openai_image_size)
                        url = ImageService.public_url(user["_id"], image_doc["filename"])
                        artifacts = [{"type": "image", "url": url, "filename": image_doc["filename"], "prompt": prompt}]
                        final_text = f"Done. Generated image: {url}"
                    else:
                        m = re.search(r"\b([0-9a-fA-F]{24})\b", message)
                        if m:
                            file_id = m.group(1)
                            question = message.replace(file_id, "").strip() or "Summarize this PDF."
                            await send({"type": "progress", "action": "assistant", "job_id": job_id, "stage": "ask_pdf"})

                            file_doc = await FilesRepo.get_file(user["_id"], file_id)
                            if not file_doc:
                                final_text = "I couldn't find that file_id in your account."
                            else:
                                all_chunks = await FilesRepo.get_chunks_for_file(user["_id"], file_id, limit=3000)
                                top_k = await PdfService.retrieve_top_k(question, all_chunks, k=settings.rag_top_k)

                                context_lines = [f"[{i}] (page {ch['page']}) {ch['text']}" for i, ch in enumerate(top_k, start=1)]
                                system = (
                                    "You answer strictly from the provided PDF snippets. "
                                    "If the answer is not in the snippets, say you don't know. "
                                    "Cite sources like [1], [2] referencing the snippet numbers."
                                )
                                user_prompt = "PDF snippets:\n" + "\n\n".join(context_lines) + f"\n\nQuestion: {question}"
                                openai_input = [{"role": "system", "content": system}, {"role": "user", "content": user_prompt}]

                                async for delta in ChatService.stream_reply(openai_input):
                                    final_text += delta
                                    await send({"type": "delta", "job_id": job_id, "delta": delta})

                                citations = [{"snippet": i + 1, "page": ch["page"]} for i, ch in enumerate(top_k)]
                                artifacts = [{"type": "pdf_citations", "file_id": file_id, "citations": citations}]
                        else:
                            history = await ChatRepo.get_messages(user["_id"], conversation_id_local, limit=50)
                            openai_input = [{"role": "system", "content": "You are a helpful assistant."}]
                            for mm in history:
                                r = mm.get("role", "user")
                                if r not in ("user", "assistant", "system"):
                                    r = "user"
                                openai_input.append({"role": r, "content": mm.get("content", "")})
                            async for delta in ChatService.stream_reply(openai_input):
                                final_text += delta
                                await send({"type": "delta", "job_id": job_id, "delta": delta})

                    await ChatRepo.add_message(
                        user_id=user["_id"],
                        conversation_id=conversation_id_local,
                        role="assistant",
                        content=final_text,
                        meta={"provider": "openai", "model": settings.openai_model, "artifacts": artifacts},
                    )
                    await ChatRepo.touch_conversation(user["_id"], conversation_id_local)

                    await send(
                        {
                            "type": "result",
                            "action": "assistant",
                            "job_id": job_id,
                            "conversation_id": conversation_id_local,
                            "message": final_text,
                            "artifacts": artifacts,
                        }
                    )
                    continue

                if action == "chat":
                    job_id = data.get("job_id") or f"job_{id(ws)}"
                    conversation_id = data.get("conversation_id")
                    message = (data.get("message") or "").strip()

                    if not message:
                        await send({"type": "error", "job_id": job_id, "error": "Missing message"})
                        continue

                    task = asyncio.create_task(handle_chat(job_id, conversation_id, message))
                    running_jobs[job_id] = task
                    continue

                if action == "cancel":
                    job_id = data.get("job_id")
                    t = running_jobs.get(job_id)
                    if t and not t.done():
                        t.cancel()
                        await send({"type": "cancelling", "job_id": job_id})
                    else:
                        await send({"type": "error", "error": "Job not found or already finished", "job_id": job_id})
                    continue

                if action == "list_conversations":
                    convs = await ChatRepo.list_conversations(user["_id"], limit=int(data.get("limit") or 50))
                    await send({"type": "result", "action": "list_conversations", "conversations": convs})
                    continue

                if action == "get_messages":
                    conversation_id = data.get("conversation_id")
                    msgs = await ChatRepo.get_messages(user["_id"], conversation_id, limit=int(data.get("limit") or 50))
                    await send({"type": "result", "action": "get_messages", "messages": msgs})
                    continue

                if action == "upload_pdf":
                    job_id = data.get("job_id") or f"job_{id(ws)}"
                    conversation_id = data.get("conversation_id")
                    filename = data.get("filename") or "upload.pdf"
                    content_b64 = data.get("content_b64") or ""

                    if not content_b64:
                        await send({"type": "error", "job_id": job_id, "error": "Missing content_b64"})
                        continue

                    await send({"type": "started", "action": "upload_pdf", "job_id": job_id})

                    pdf_bytes = base64.b64decode(content_b64)
                    storage_path = PdfService.save_pdf_bytes(user["_id"], pdf_bytes, filename)

                    file_doc = await FilesRepo.create_file(
                        user_id=user["_id"],
                        conversation_id=conversation_id,
                        filename=filename,
                        storage_path=storage_path,
                        size_bytes=len(pdf_bytes),
                    )

                    await send({"type": "progress", "action": "upload_pdf", "job_id": job_id, "stage": "extract_text"})
                    pages = PdfService.read_pdf_text_by_page(storage_path)

                    await send({"type": "progress", "action": "upload_pdf", "job_id": job_id, "stage": "chunk_embed"})
                    chunk_docs = await PdfService.chunk_and_embed_pages(
                        user_id=user["_id"],
                        file_id=file_doc["_id"],
                        conversation_id=conversation_id,
                        pages=pages,
                    )
                    inserted = await FilesRepo.insert_chunks(chunk_docs)

                    await send(
                        {
                            "type": "result",
                            "action": "upload_pdf",
                            "job_id": job_id,
                            "file": file_doc,
                            "pages": len(pages),
                            "chunks": inserted,
                        }
                    )
                    continue

                if action == "ask_pdf":
                    job_id = data.get("job_id") or f"job_{id(ws)}"
                    file_id = data.get("file_id")
                    question = (data.get("question") or "").strip()
                    conversation_id = data.get("conversation_id")
                    top_k_req = int(data.get("top_k") or settings.rag_top_k)

                    if not file_id:
                        await send({"type": "error", "job_id": job_id, "error": "Missing file_id"})
                        continue
                    if not question:
                        await send({"type": "error", "job_id": job_id, "error": "Missing question"})
                        continue

                    await send({"type": "started", "action": "ask_pdf", "job_id": job_id})

                    conv = await ChatRepo.ensure_conversation(user["_id"], conversation_id, title="New chat")
                    if not conv:
                        await send({"type": "error", "job_id": job_id, "error": "Conversation not found"})
                        continue
                    conversation_id_local = conv["_id"]

                    await ChatRepo.add_message(
                        user_id=user["_id"],
                        conversation_id=conversation_id_local,
                        role="user",
                        content=question,
                        meta={"kind": "ask_pdf", "file_id": file_id},
                    )
                    await ChatRepo.touch_conversation(user["_id"], conversation_id_local)

                    file_doc = await FilesRepo.get_file(user["_id"], file_id)
                    if not file_doc:
                        await send({"type": "error", "job_id": job_id, "error": "File not found"})
                        continue

                    all_chunks = await FilesRepo.get_chunks_for_file(user["_id"], file_id, limit=3000)
                    top_chunks = await PdfService.retrieve_top_k(question, all_chunks, k=top_k_req)

                    context_lines = []
                    for i, ch in enumerate(top_chunks, start=1):
                        context_lines.append(f"[{i}] (page {ch['page']}) {ch['text']}")

                    system = (
                        "You answer strictly from the provided PDF snippets.\n"
                        "If the answer is not in the snippets, say you don't know.\n"
                        "Cite sources like [1], [2] referencing the snippet numbers."
                    )
                    user_prompt = "PDF snippets:\n" + "\n\n".join(context_lines) + f"\n\nQuestion: {question}"

                    openai_input = [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_prompt},
                    ]

                    full = ""
                    async for delta in ChatService.stream_reply(openai_input):
                        full += delta
                        await send({"type": "delta", "job_id": job_id, "delta": delta})

                    citations = [{"snippet": i + 1, "page": ch["page"]} for i, ch in enumerate(top_chunks)]

                    await ChatRepo.add_message(
                        user_id=user["_id"],
                        conversation_id=conversation_id_local,
                        role="assistant",
                        content=full,
                        meta={"kind": "ask_pdf", "file_id": file_id, "citations": citations},
                    )
                    await ChatRepo.touch_conversation(user["_id"], conversation_id_local)

                    await send(
                        {
                            "type": "result",
                            "action": "ask_pdf",
                            "job_id": job_id,
                            "conversation_id": conversation_id_local,
                            "answer": full,
                            "citations": citations,
                        }
                    )
                    continue

                if action == "image_generate":
                    job_id = data.get("job_id") or f"job_{id(ws)}"
                    prompt = (data.get("prompt") or "").strip()
                    size = data.get("size") or settings.openai_image_size

                    if not prompt:
                        await send({"type": "error", "job_id": job_id, "error": "Missing prompt"})
                        continue

                    allowed, used, limit = UsageService.add_and_check(user["_id"], user.get("plan", "free"), "image", 1)
                    if not allowed:
                        await send({"type": "error", "error": "Quota exceeded", "kind": "image", "used": used, "limit": limit, "job_id": job_id})
                        continue
                    await UsageRepo.log_event(user["_id"], "image", 1, meta={"source": "ws_image_generate"})

                    await send({"type": "started", "action": "image_generate", "job_id": job_id})

                    image_doc = await ImageService.generate_and_save(user_id=user["_id"], prompt=prompt, size=size)
                    url = ImageService.public_url(user["_id"], image_doc["filename"])

                    await send(
                        {
                            "type": "result",
                            "action": "image_generate",
                            "job_id": job_id,
                            "image": {
                                "url": url,
                                "filename": image_doc["filename"],
                                "prompt": prompt,
                                "size": size,
                            },
                        }
                    )
                    continue

                if action == "image_public_link":
                    job_id = data.get("job_id") or f"job_{id(ws)}"
                    filename = (data.get("filename") or "").strip()
                    ttl_sec = int(data.get("ttl_sec") or 600)

                    if not filename:
                        await send({"type": "error", "job_id": job_id, "error": "Missing filename"})
                        continue

                    await send({"type": "started", "action": "image_public_link", "job_id": job_id})
                    url = await ImageService.create_public_link(user["_id"], filename, ttl_sec=ttl_sec)

                    await send({"type": "result", "action": "image_public_link", "job_id": job_id, "url": url, "ttl_sec": ttl_sec})
                    continue

                if action == "mcp_tool_list":
                    job_id = data.get("job_id") or f"job_{id(ws)}"
                    await send({"type": "started", "action": "mcp_tool_list", "job_id": job_id})
                    client = MCPClient(settings.mcp_base_url)
                    tools = await client.list_tools()
                    await send({"type": "result", "action": "mcp_tool_list", "job_id": job_id, "tools": tools})
                    continue

                if action == "mcp_tool_call":
                    job_id = data.get("job_id") or f"job_{id(ws)}"
                    tool = data.get("tool")
                    args = data.get("args") or {}
                    await send({"type": "started", "action": "mcp_tool_call", "job_id": job_id})
                    client = MCPClient(settings.mcp_base_url)
                    result = await client.call_tool(tool, args)
                    await send({"type": "result", "action": "mcp_tool_call", "job_id": job_id, "tool": tool, "result": result})
                    continue

                if action == "tool_list":
                    job_id = data.get("job_id") or f"job_{id(ws)}"
                    await send({"type": "started", "action": "tool_list", "job_id": job_id})
                    await send({"type": "result", "action": "tool_list", "job_id": job_id, "tools": []})
                    continue

                if action == "ping":
                    await send({"type": "pong", "ts": datetime.now(timezone.utc).isoformat()})
                    continue

                await send({"type": "error", "error": f"Unknown action: {action}"})

            except Exception as e:
                await send({"type": "error", "error": f"{type(e).__name__}: {e}"})
                continue

    except WebSocketDisconnect:
        for t in running_jobs.values():
            if not t.done():
                t.cancel()
        return