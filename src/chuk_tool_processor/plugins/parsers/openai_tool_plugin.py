# chuk_tool_processor/parsers/openai_tool_plugin.py
"""
Parser for OpenAI Chat-Completions responses that contain a `tool_calls` array.
"""

from __future__ import annotations

import json
from typing import Any, List

from pydantic import ValidationError

from .base import ParserPlugin
from chuk_tool_processor.models.tool_call import ToolCall


class OpenAIToolPlugin(ParserPlugin):
    """
    Understands responses that look like:

    {
        "tool_calls": [
            {
                "id": "call_abc",
                "type": "function",
                "function": {
                    "name": "weather",
                    "arguments": "{\"location\": \"New York\"}"
                }
            },
            …
        ]
    }
    """

    def try_parse(self, raw: str | Any) -> List[ToolCall]:
        # ------------------------------------------------------------------ #
        # Parse the incoming JSON (string or already-dict)
        # ------------------------------------------------------------------ #
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, json.JSONDecodeError):
            return []

        if not isinstance(data, dict) or "tool_calls" not in data:
            return []

        # ------------------------------------------------------------------ #
        # Convert each entry into a ToolCall
        # ------------------------------------------------------------------ #
        calls: List[ToolCall] = []
        for tc in data["tool_calls"]:
            fn = tc.get("function", {})
            name = fn.get("name")
            args = fn.get("arguments", {})

            if not isinstance(name, str) or not name:
                continue

            # arguments come back as a JSON-encoded string – decode if needed
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}

            if not isinstance(args, dict):
                args = {}

            try:
                # `tool` must match the **registry key** (e.g. "weather")
                calls.append(ToolCall(tool=name, arguments=args))
            except ValidationError:
                continue  # skip malformed entries

        return calls
