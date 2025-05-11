# chuk_tool_processor/parsers/openai_tool_plugin.py
"""Async parser for OpenAI Chat-Completions `tool_calls` arrays."""
from __future__ import annotations

import json
from typing import Any, List

from pydantic import ValidationError

from chuk_tool_processor.models.tool_call import ToolCall
from .base import ParserPlugin


class OpenAIToolPlugin(ParserPlugin):
    """
    Understands structures like::

        {
            "tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {
                        "name": "weather",
                        "arguments": "{\"location\": \"New York\"}"
                    }
                }
            ]
        }
    """

    async def try_parse(self, raw: str | Any) -> List[ToolCall]:  # noqa: D401
        # 1. Load JSON if necessary
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, json.JSONDecodeError):
            return []

        if not isinstance(data, dict) or "tool_calls" not in data:
            return []

        out: List[ToolCall] = []
        for tc in data["tool_calls"]:
            fn = tc.get("function", {})
            name = fn.get("name")
            args = fn.get("arguments", {})

            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}

            if isinstance(name, str) and name:
                try:
                    out.append(ToolCall(tool=name, arguments=args if isinstance(args, dict) else {}))
                except ValidationError:
                    continue

        return out
