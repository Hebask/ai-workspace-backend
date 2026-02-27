from __future__ import annotations
from typing import Any, Dict, List

def tool_schemas() -> List[Dict[str, Any]]:
    # Chat Completions format:
    return [
        {
            "type": "function",
            "function": {
                "name": "ask_pdf",
                "description": "Answer a question using an uploaded PDF (RAG). Requires file_id and question.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_id": {"type": "string"},
                        "question": {"type": "string"},
                        "top_k": {"type": "integer", "default": 5},
                    },
                    "required": ["file_id", "question"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "image_generate",
                "description": "Generate an image from a text prompt and return a URL.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "size": {"type": "string", "default": "1024x1024"},
                    },
                    "required": ["prompt"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "mcp_tool_run",
                "description": "Run a tool exposed by the MCP server.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "args": {"type": "object"},
                    },
                    "required": ["name"],
                    "additionalProperties": True,
                },
            },
        },
    ]