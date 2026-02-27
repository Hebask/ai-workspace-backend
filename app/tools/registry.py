from __future__ import annotations

from typing import Callable, Any, Dict, Optional

ToolFn = Callable[[dict], Any]


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolFn] = {}

    def register(self, name: str, fn: ToolFn):
        self._tools[name] = fn

    def get(self, name: str) -> Optional[ToolFn]:
        return self._tools.get(name)

    def list(self) -> list[str]:
        return sorted(self._tools.keys())


TOOLS = ToolRegistry()