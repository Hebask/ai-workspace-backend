from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from app.core.config import settings
from app.services.openai_client import get_openai_client
from app.repositories.files_repo import FilesRepo
from app.services.pdf_service import PdfService
from app.services.image_service import ImageService
from app.tools.mcp_client import MCPClient
from app.agents.tool_schemas import tool_schemas


def _extract_file_id(text: str) -> str | None:
    m = re.search(r"\bfile_id\s+([a-fA-F0-9]{12,})\b", text)
    return m.group(1) if m else None


async def _run_ask_pdf(user_id: str, file_id: str, question: str, top_k: int) -> Dict[str, Any]:
    all_chunks = await FilesRepo.get_chunks_for_file(user_id, file_id, limit=3000)
    if not all_chunks:
        return {"ok": False, "error": "No chunks found for this file (is it embedded?)"}

    top_chunks = await PdfService.retrieve_top_k(question, all_chunks, k=top_k)

    context_lines = []
    for i, ch in enumerate(top_chunks, start=1):
        context_lines.append(f"[{i}] (page {ch['page']}) {ch['text']}")

    return {
        "ok": True,
        "data": {
            "snippets": context_lines,
            "citations": [{"snippet": i + 1, "page": ch["page"]} for i, ch in enumerate(top_chunks)],
        },
    }


async def _run_image(user_id: str, prompt: str, size: str | None) -> Dict[str, Any]:
    info = await ImageService.generate_and_save(user_id, prompt=prompt, size=size)
    url = f"{settings.public_base_url}/images/{user_id}/{info['filename']}"
    return {"ok": True, "data": {"url": url, "filename": info["filename"], "model": info["model"], "size": info["size"]}}


async def _run_mcp(name: str, args: dict) -> Dict[str, Any]:
    client = MCPClient(settings.mcp_base_url)
    out = await client.call_tool(name, args or {})
    return {"ok": True, "data": out}


async def agent_run_chat_tools(
    user: dict,
    user_message: str,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Tool loop using Chat Completions tool calling (stable):
    - planning call (non-stream) to see tool_calls
    - execute tools
    - loop until no tool_calls
    - final streaming answer
    """
    client = get_openai_client()
    tools = tool_schemas()
    artifacts: List[Dict[str, Any]] = []

    hinted_file_id = _extract_file_id(user_message)

    system = (
        "You are an assistant in a multi-tool app.\n"
        "Use tools when needed:\n"
        "- ask_pdf(file_id, question, top_k)\n"
        "- image_generate(prompt, size)\n"
        "- mcp_tool_run(name, args)\n"
        "If you need file_id and none is provided, ask for it.\n"
        "Cite PDF sources like [1], [2] based on snippets.\n"
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_message},
    ]

    for _ in range(settings.agent_max_hops):
        # Planning/tool call step (non-stream)
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)

        # No tool calls -> stream final answer
        if not tool_calls:
            final_text = ""
            stream = await client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                stream=True,
            )
            async for event in stream:
                delta = event.choices[0].delta
                if getattr(delta, "content", None):
                    final_text += delta.content
            return final_text, artifacts

        # Append assistant tool-call message
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
        )

        # Execute tool calls
        for tc in tool_calls:
            name = tc.function.name
            args_raw = tc.function.arguments or "{}"
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
            except Exception:
                args = {}

            if name == "ask_pdf":
                file_id = args.get("file_id") or hinted_file_id or ""
                question = args.get("question") or user_message
                top_k = int(args.get("top_k") or settings.rag_top_k)

                out = await _run_ask_pdf(user["_id"], file_id, question, top_k)
                if out.get("ok") and out.get("data", {}).get("citations"):
                    artifacts.append({"type": "pdf_citations", "citations": out["data"]["citations"]})

                # Provide snippets back to model
                payload = out
                if out.get("ok"):
                    payload = {
                        "ok": True,
                        "data": {
                            "snippets": out["data"]["snippets"],
                            "citations": out["data"]["citations"],
                        },
                    }

            elif name == "image_generate":
                out = await _run_image(user["_id"], args.get("prompt") or user_message, args.get("size"))
                if out.get("ok") and out.get("data", {}).get("url"):
                    artifacts.append({"type": "image", "image": out["data"]})
                payload = out

            elif name == "mcp_tool_run":
                out = await _run_mcp(args.get("name", ""), args.get("args") or {})
                artifacts.append({"type": "mcp", "output": out})
                payload = out

            else:
                payload = {"ok": False, "error": f"Unknown tool: {name}"}

            # Tool message MUST include tool_call_id
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(payload, ensure_ascii=False),
                }
            )

    return "I couldn’t complete the request within the tool limit. Please try a simpler request.", artifacts