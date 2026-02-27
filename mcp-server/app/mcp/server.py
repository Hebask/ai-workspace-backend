from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

app = FastAPI(title="MCP Server (Minimal)", version="0.1.0")


# -----------------------
# Tool registry
# -----------------------
Tool = Dict[str, Any]

def tool_list() -> List[Tool]:
    return [
        {
            "name": "ping",
            "description": "Health check tool",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": True},
        },
        {
            "name": "echo",
            "description": "Echo back provided text",
            "input_schema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": True,
            },
        },
    ]


def run_tool(name: str, arguments: dict) -> dict:
    if name == "ping":
        return {"ok": True, "data": {"message": "pong"}}

    if name == "echo":
        return {"ok": True, "data": {"text": arguments.get("text", "")}}

    return {"ok": False, "error": f"Unknown tool: {name}"}


# -----------------------
# HTTP API
# -----------------------
class ToolCall(BaseModel):
    name: str
    arguments: Dict[str, Any] = {}


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/tools/list")
async def tools_list():
    return tool_list()


@app.post("/tools/call")
async def tools_call(req: ToolCall):
    out = run_tool(req.name, req.arguments or {})
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error", "Tool failed"))
    return out
