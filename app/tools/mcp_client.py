from __future__ import annotations

import httpx
from app.core.config import settings


class MCPClient:
    """
    Minimal MCP HTTP bridge.
    Assumes MCP server exposes:
      POST {base_url}/tools/list
      POST {base_url}/tools/call  { "name": "...", "arguments": {...} }
    Adjust routes later if MCP server differs.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def list_tools(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=60) as http:
            r = await http.post(f"{self.base_url}/tools/list", json={})
            r.raise_for_status()
            return r.json()

    async def call_tool(self, name: str, arguments: dict) -> dict:
        async with httpx.AsyncClient(timeout=300) as http:
            r = await http.post(f"{self.base_url}/tools/call", json={"name": name, "arguments": arguments})
            r.raise_for_status()
            return r.json()