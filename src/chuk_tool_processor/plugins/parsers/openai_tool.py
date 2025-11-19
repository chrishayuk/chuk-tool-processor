# chuk_tool_processor/plugins/parsers/openai_tool.py
"""Async parser for OpenAI-style `tool_calls` arrays."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.plugins.parsers.base import ParserPlugin
from chuk_tool_processor.utils import fast_json as json

__all__ = ["OpenAIToolPlugin"]

logger = get_logger(__name__)


class PluginMeta:
    """Optional descriptor consumed by the plugin-discovery system."""

    name: str = "openai_tool_calls"
    description: str = "Parses Chat-Completions responses containing `tool_calls`."
    version: str = "1.0.0"
    author: str = "chuk_tool_processor"


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

    async def try_parse(self, raw: str | Any) -> list[ToolCall]:  # noqa: D401
        # ------------------------------------------------------------------ #
        # 1. Decode JSON when the input is a string
        # ------------------------------------------------------------------ #
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            logger.debug("openai_tool_plugin: input is not valid JSON")
            return []

        if not isinstance(data, dict) or "tool_calls" not in data:
            return []

        # ------------------------------------------------------------------ #
        # 2. Build ToolCall objects
        # ------------------------------------------------------------------ #
        calls: list[ToolCall] = []

        # Ensure tool_calls is a list
        tool_calls = data.get("tool_calls", [])
        if not isinstance(tool_calls, list):
            return []

        for entry in tool_calls:
            fn = entry.get("function", {})
            name = fn.get("name")
            args = fn.get("arguments", {})

            # Arguments may be double-encoded JSON
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}

            if not isinstance(name, str) or not name:
                continue

            try:
                calls.append(ToolCall(tool=name, arguments=args if isinstance(args, dict) else {}))
            except ValidationError:
                logger.debug(
                    "openai_tool_plugin: validation error while building ToolCall for %s",
                    name,
                )

        return calls
