# chuk_tool_processor/plugins/parsers/json_tool.py
"""Async JSON `tool_calls` parser plugin."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.plugins.parsers.base import ParserPlugin
from chuk_tool_processor.utils import fast_json as json

__all__ = ["JsonToolPlugin"]

logger = get_logger(__name__)


class PluginMeta:
    """Optional self-description consumed by the plugin-discovery subsystem."""

    name: str = "json_tool_calls"
    description: str = "Parses a JSON object containing a `tool_calls` array."
    version: str = "1.0.0"
    author: str = "chuk_tool_processor"


class JsonToolPlugin(ParserPlugin):
    """Extracts a *list* of :class:`ToolCall` objects from a `tool_calls` array."""

    async def try_parse(self, raw: str | Any) -> list[ToolCall]:  # noqa: D401
        # Decode JSON if we were given a string
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            logger.debug("json_tool: input is not valid JSON")
            return []

        if not isinstance(data, dict):
            return []

        calls: list[ToolCall] = []
        for entry in data.get("tool_calls", []):
            try:
                calls.append(ToolCall(**entry))
            except ValidationError:
                logger.debug("json_tool: validation error on entry %s", entry)
                continue

        return calls
