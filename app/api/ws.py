from __future__ import annotations
from app.models import message, user
from app.tools.registry import TOOLS
from app.tools.mcp_client import MCPClient
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import asyncio
from datetime import datetime
from bson import ObjectId
from app.repositories.users_repo import UsersRepo
from app.services.usage_service import UsageService
from app.repositories.usage_repo import UsageRepo
from app.core.config import settings
from app.core.security import decode_token
from app.repositories.chat_repo import ChatRepo
from app.repositories.files_repo import FilesRepo
from app.services.chat_service import ChatService
from app.services.pdf_service import PdfService
from app.services.image_service import ImageService
from app.agents.assistant_agent import agent_run_chat_tools

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

            # create conversation if not provided
            if not conversation_id:
                conv = await ChatRepo.create_conversation(user["_id"], title="New chat")
                conversation_id_local = conv["_id"]
                await send({"type": "conversation", "job_id": job_id, "conversation_id": conversation_id_local})
            else:
                conv = await ChatRepo.get_conversation(user["_id"], conversation_id)
                if not conv:
                    await send({"type": "error", "job_id": job_id, "error": "Conversation not found"})
                    return
                conversation_id_local = conversation_id

            # store user message
            await ChatRepo.add_message(
                user_id=user["_id"],
                conversation_id=conversation_id_local,
                role="user",
                content=message,
            )

            # Build conversation history for the model
            history = await ChatRepo.get_messages(user["_id"], conversation_id_local, limit=50)

            openai_input = [{"role": "system", "content": "You are a helpful assistant."}]
            for m in history:
                role = m.get("role", "user")
                if role not in ("user", "assistant", "system"):
                    role = "user"
                openai_input.append({"role": role, "content": m.get("content", "")})

            # Stream from OpenAI
            full = ""
            async for delta in ChatService.stream_reply(openai_input):
                full += delta
                await send({"type": "delta", "job_id": job_id, "delta": delta})

            # store assistant message
            await ChatRepo.add_message(
                user_id=user["_id"],
                conversation_id=conversation_id_local,
                role="assistant",
                content=full,
                meta={"provider": "openai"},
            )

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

            # 1) Safe JSON parsing
            try:
                data = json.loads(raw)
            except Exception:
                await send({"type": "error", "error": "Invalid JSON"})
                continue

            # 2) Safe action handling (never disconnect on exception)
            try:
                action = data.get("action")

                # -------------------------
                # AUTH
                # -------------------------
                if action == "auth":
                    token = (data.get("token") or "").strip()
                    if not token:
                        await send({"type": "error", "error": "Missing token"})
                        continue

                    if token.startswith("Bearer "):
                        token = token.split(" ", 1)[1].strip()

                    try:
                        payload = decode_token(token)
                    except Exception as e:
                        await send({"type": "error", "error": f"Token error: {type(e).__name__}: {e}"})
                        continue

                    if payload.get("type") != "access":
                        await send({"type": "error", "error": "Invalid token type"})
                        continue

                    db_user = await UsersRepo.get_by_id(payload["sub"])
                    plan = (db_user or {}).get("plan", "free") if db_user else "free"
                    user = {"_id": payload["sub"], "email": payload.get("email"), "plan": plan}

                    await send({"type": "authed", "user": user})
                    continue

                # block any other actions until authed
                if not user:
                    await send(
                        {
                            "type": "error",
                            "error": "Not authenticated. Send {action:'auth', token:'...'} first.",
                        }
                    )
                    continue

                if action == "assistant":
                    job_id = data.get("job_id") or f"job_{id(ws)}"
                    message = (data.get("message") or "").strip()
                    conversation_id = data.get("conversation_id")

                    if not message:
                        await send({"type": "error", "job_id": job_id, "error": "Missing message"})
                        continue

                    await send({"type": "started", "action": "assistant", "job_id": job_id})

                    # quota: count 1 chat
                    allowed, used, limit = UsageService.add_and_check(user["_id"], user.get("plan", "free"), "chat", 1)
                    if not allowed:
                        await send({"type": "error", "error": "Quota exceeded", "kind": "chat", "used": used, "limit": limit, "job_id": job_id})
                        continue
                    await UsageRepo.log_event(user["_id"], "chat", 1, meta={"source": "ws_assistant"})

                    # 1) Ensure conversation exists (or validate provided one)
                    conv = await ChatRepo.ensure_conversation(user["_id"], conversation_id, title="New chat")
                    if not conv:
                        await send({"type": "error", "job_id": job_id, "error": "Conversation not found"})
                        continue

                    conversation_id_local = conv["_id"]

                    # 2) Store user message
                    await ChatRepo.add_message(
                        user_id=user["_id"],
                        conversation_id=conversation_id_local,
                        role="user",
                        content=message,
                    )
                    await ChatRepo.touch_conversation(user["_id"], conversation_id_local)

                    # 3) Run agent
                    final_text, artifacts = await agent_run_chat_tools(user, message)

                    # 4) Stream deltas (simple chunk streaming)
                    chunk = 40
                    for i in range(0, len(final_text), chunk):
                        await send({"type": "delta", "job_id": job_id, "delta": final_text[i:i+chunk]})

                    # 5) Store assistant message (including artifacts)
                    await ChatRepo.add_message(
                        user_id=user["_id"],
                        conversation_id=conversation_id_local,
                        role="assistant",
                        content=final_text,
                        meta={
                            "provider": "openai",
                            "model": settings.openai_model,
                            "artifacts": artifacts,
                        },
                    )
                    await ChatRepo.touch_conversation(user["_id"], conversation_id_local)

                    # 6) Return result + conversation_id always
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

                # -------------------------
                # CHAT
                # -------------------------
                if action == "chat":
                    job_id = data.get("job_id") or f"job_{id(ws)}"
                    conversation_id = data.get("conversation_id")
                    message = data.get("message") or ""
                    allowed, used, limit = UsageService.add_and_check(user["_id"], user.get("plan", "free"), "chat", 1)
                    if not allowed:
                        await send({"type": "error", "error": "Quota exceeded", "kind": "chat", "used": used, "limit": limit})
                        continue

                    # log usage event (async)
                    await UsageRepo.log_event(user["_id"], "chat", 1, meta={"source": "ws"})
                    task = asyncio.create_task(handle_chat(job_id, conversation_id, message))
                    running_jobs[job_id] = task
                    continue
                # -------------------------
                # IMAGE GENERATION 
                # -------------------------
                if action == "image_generate":
                    job_id = data.get("job_id") or f"job_{id(ws)}"
                    prompt = (data.get("prompt") or "").strip()
                    size = (data.get("size") or "").strip() or None

                    if not prompt:
                        await send({"type": "error", "job_id": job_id, "error": "Missing prompt"})
                        continue

                    # quota: 1 image
                    allowed, used, limit = UsageService.add_and_check(user["_id"], user.get("plan", "free"), "image", 1)
                    if not allowed:
                        await send({"type": "error", "error": "Quota exceeded", "kind": "image", "used": used, "limit": limit, "job_id": job_id})
                        continue

                    await UsageRepo.log_event(user["_id"], "image", 1, meta={"source": "ws"})

                    await send({"type": "started", "action": "image_generate", "job_id": job_id})

                    info = await ImageService.generate_and_save(user["_id"], prompt=prompt, size=size)

                    # build a public URL that the frontend can display
                    url = f"{settings.public_base_url}/images/{user['_id']}/{info['filename']}"

                    await send(
                        {
                            "type": "result",
                            "action": "image_generate",
                            "job_id": job_id,
                            "image": {
                                "url": url,
                                "filename": info["filename"],
                                "size": info["size"],
                                "model": info["model"],
                            },
                        }
                    )
                    continue
                
                # -------------------------
                # CANCEL
                # -------------------------
                if action == "cancel":
                    job_id = data.get("job_id")
                    t = running_jobs.get(job_id)
                    if t and not t.done():
                        t.cancel()
                        await send({"type": "cancelling", "job_id": job_id})
                    else:
                        await send({"type": "error", "error": "Job not found or already finished", "job_id": job_id})
                    continue

                if action == "image_public_link":
                    job_id = data.get("job_id") or f"job_{id(ws)}"
                    filename = data.get("filename")
                    if not filename:
                        await send({"type": "error", "job_id": job_id, "error": "Missing filename"})
                        continue

                    from app.services.public_link_service import PublicLinkService
                    token = PublicLinkService.create_image_token(user["_id"], filename, ttl_sec=int(data.get("ttl_sec") or 300))
                    url = f"{settings.public_base_url}/images/public/{token}"

                    await send({"type": "result", "action": "image_public_link", "job_id": job_id, "url": url, "ttl_sec": int(data.get('ttl_sec') or 300)})
                    continue

                # -------------------------
                # LIST CONVERSATIONS
                # -------------------------
                if action == "list_conversations":
                    convs = await ChatRepo.list_conversations(user["_id"], limit=int(data.get("limit") or 50))
                    await send({"type": "result", "action": "list_conversations", "conversations": convs})
                    continue

                if action == "tool_list":
                    await send({"type": "result", "action": "tool_list", "tools": TOOLS.list()})
                    continue

                if action == "tool_run":
                    job_id = data.get("job_id") or f"job_{id(ws)}"
                    name = data.get("name")
                    args = data.get("args") or {}

                    fn = TOOLS.get(name or "")
                    if not fn:
                        await send({"type": "error", "job_id": job_id, "error": f"Unknown tool: {name}"})
                        continue

                    await send({"type": "started", "action": "tool_run", "job_id": job_id, "name": name})
                    try:
                        out = fn(args)
                        await send({"type": "result", "action": "tool_run", "job_id": job_id, "name": name, "output": out})
                    except Exception as e:
                        await send({"type": "error", "job_id": job_id, "error": f"{type(e).__name__}: {e}"})
                    continue

                if action == "mcp_tool_list":
                    job_id = data.get("job_id") or f"job_{id(ws)}"
                    await send({"type": "started", "action": "mcp_tool_list", "job_id": job_id})
                    client = MCPClient(settings.mcp_base_url)
                    try:
                        tools = await client.list_tools()
                        await send({"type": "result", "action": "mcp_tool_list", "job_id": job_id, "tools": tools})
                    except Exception as e:
                        await send({"type": "error", "job_id": job_id, "error": f"{type(e).__name__}: {e}"})
                    continue

                if action == "mcp_tool_run":
                    job_id = data.get("job_id") or f"job_{id(ws)}"
                    name = data.get("name")
                    args = data.get("args") or {}
                    if not name:
                        await send({"type": "error", "job_id": job_id, "error": "Missing name"})
                        continue

                    await send({"type": "started", "action": "mcp_tool_run", "job_id": job_id, "name": name})
                    client = MCPClient(settings.mcp_base_url)
                    try:
                        out = await client.call_tool(name, args)
                        await send({"type": "result", "action": "mcp_tool_run", "job_id": job_id, "name": name, "output": out})
                    except Exception as e:
                        await send({"type": "error", "job_id": job_id, "error": f"{type(e).__name__}: {e}"})
                    continue

                # -------------------------
                # GET MESSAGES
                # -------------------------
                if action == "get_messages":
                    conversation_id = data.get("conversation_id")
                    msgs = await ChatRepo.get_messages(user["_id"], conversation_id, limit=int(data.get("limit") or 50))
                    await send({"type": "result", "action": "get_messages", "messages": msgs})
                    continue

                if action == "job_status":
                    job_id = data.get("job_id")
                    if not job_id:
                        await send({"type": "error", "error": "Missing job_id"})
                        continue

                    from app.services.job_service import JobService
                    st = JobService.get(job_id)
                    if not st:
                        await send({"type": "error", "error": "Job not found", "job_id": job_id})
                        continue

                    # ownership check
                    payload = st.get("payload") or {}
                    if payload.get("user_id") and payload["user_id"] != user["_id"]:
                        await send({"type": "error", "error": "Forbidden", "job_id": job_id})
                        continue

                    await send({"type": "result", "action": "job_status", "job_id": job_id, "status": st})
                    continue


                if action == "cancel_job":
                    job_id = data.get("job_id")
                    if not job_id:
                        await send({"type": "error", "error": "Missing job_id"})
                        continue

                    from app.services.job_service import JobService
                    st = JobService.get(job_id)
                    if not st:
                        await send({"type": "error", "error": "Job not found", "job_id": job_id})
                        continue

                    payload = st.get("payload") or {}
                    if payload.get("user_id") and payload["user_id"] != user["_id"]:
                        await send({"type": "error", "error": "Forbidden", "job_id": job_id})
                        continue

                    JobService.request_cancel(job_id)
                    await send({"type": "result", "action": "cancel_job", "job_id": job_id, "message": "Cancel requested"})
                    continue

                # -------------------------
                # ASK PDF (RAG)
                # -------------------------
                if action == "ask_pdf":
                    job_id = data.get("job_id") or f"job_{id(ws)}"
                    file_id = data.get("file_id")
                    question = (data.get("question") or "").strip()
                    top_k_req = int(data.get("top_k") or settings.rag_top_k)

                    if not file_id:
                        await send({"type": "error", "job_id": job_id, "error": "Missing file_id"})
                        continue
                    if not question:
                        await send({"type": "error", "job_id": job_id, "error": "Missing question"})
                        continue

                    await send({"type": "started", "action": "ask_pdf", "job_id": job_id})

                    file_doc = await FilesRepo.get_file(user["_id"], file_id)
                    if not file_doc:
                        await send({"type": "error", "job_id": job_id, "error": "File not found"})
                        continue

                    all_chunks = await FilesRepo.get_chunks_for_file(user["_id"], file_id, limit=3000)
                    if not all_chunks:
                        await send({"type": "error", "job_id": job_id, "error": "No chunks found for this file"})
                        continue

                    top_chunks = await PdfService.retrieve_top_k(question, all_chunks, k=top_k_req)
                    pages_used = len(set([ch["page"] for ch in top_chunks])) or 1

                    allowed, used, limit = UsageService.add_and_check(user["_id"], user.get("plan", "free"), "pdf_pages", pages_used)
                    if not allowed:
                        await send({"type": "error", "error": "Quota exceeded", "kind": "pdf_pages", "used": used, "limit": limit})
                        continue

                    await UsageRepo.log_event(user["_id"], "pdf_pages", pages_used, meta={"source": "ws", "file_id": file_id})
                    # Build context with citations
                    context_lines = []
                    for i, ch in enumerate(top_chunks, start=1):
                        context_lines.append(f"[{i}] (page {ch['page']}) {ch['text']}")

                    system = (
                        "Answer strictly from the provided PDF snippets.\n"
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

                    await send(
                        {
                            "type": "result",
                            "action": "ask_pdf",
                            "job_id": job_id,
                            "answer": full,
                            "citations": [{"snippet": i + 1, "page": ch["page"]} for i, ch in enumerate(top_chunks)],
                        }
                    )
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

