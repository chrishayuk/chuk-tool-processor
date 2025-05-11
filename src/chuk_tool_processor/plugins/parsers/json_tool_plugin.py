# chuk_tool_processor/parsers/json_tool.py
"""Async JSON `tool_calls` parser plugin."""
from __future__ import annotations

import json
from typing import Any, List

from pydantic import ValidationError

from chuk_tool_processor.models.tool_call import ToolCall
from .base import ParserPlugin


class JsonToolPlugin(ParserPlugin):
    """Extract `tool_calls` arrays from generic JSON responses."""

    async def try_parse(self, raw: str | Any) -> List[ToolCall]:
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            return []

        if not isinstance(data, dict):
            return []

        out: List[ToolCall] = []
        for c in data.get("tool_calls", []):
            try:
                out.append(ToolCall(**c))
            except ValidationError:
                continue

        return out
