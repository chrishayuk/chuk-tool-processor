# chuk_tool_processor/parsers/json_tool.py
"""JSON *tool_calls* parser plugin (drop-in).

Accepts raw‐string or dict input where the top-level object includes a
``tool_calls`` array – an early OpenAI Chat Completions schema.
"""
from __future__ import annotations

import json
from typing import Any, List
from pydantic import ValidationError

# imports
from .base import ParserPlugin
from chuk_tool_processor.models.tool_call import ToolCall

class JsonToolPlugin(ParserPlugin):
    """Extracts ``tool_calls`` array from a JSON response."""

    def try_parse(self, raw: str | Any) -> List[ToolCall]:
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            return []

        if not isinstance(data, dict):
            return []

        calls = data.get("tool_calls", [])
        out: List[ToolCall] = []

        for c in calls:
            try:
                out.append(ToolCall(**c))
            except ValidationError:
                continue
        return out

