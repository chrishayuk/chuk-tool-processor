# tests/tool_processor/plugins/parsers/test_openai_tool.py
"""OpenAI *tool_calls* parser plugin.

Maps Chat-Completions native tool calls back into *ToolCall* objects using
``registry.tool_export.tool_by_openai_name``.  The import is done lazily
inside ``try_parse`` to avoid circular-import issues revealed by tests.
"""
from __future__ import annotations

import json
from typing import List, Any

from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.plugins.parsers.base import ParserPlugin

logger = get_logger("chuk_tool_processor.plugins.parser.openai_tool_plugin")


class OpenAIToolPlugin(ParserPlugin):
    """Convert Chat-Completions *tool_calls* to internal *ToolCall*s."""

    # ------------------------------------------------------------------
    def try_parse(self, raw: str | Any) -> List[ToolCall]:  # type: ignore[override]
        # lazy import to dodge circular reference during package import
        try:
            from chuk_tool_processor.registry.tool_export import tool_by_openai_name  # noqa: WPS433
        except ImportError as exc:  # pragma: no cover
            logger.warning("tool_export not available: %s", exc)
            return []

        # decode JSON if needed
        if isinstance(raw, str):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return []
        else:
            data = raw

        if not isinstance(data, dict):
            return []

        tc_list = data.get("tool_calls")
        if not isinstance(tc_list, list):
            return []

        out: List[ToolCall] = []
        for tc in tc_list:
            try:
                fn = tc["function"]
                tool_cls = tool_by_openai_name(fn["name"])
                out.append(ToolCall(tool=tool_cls.__name__, arguments=fn["arguments"]))
            except (KeyError, TypeError):
                # unknown or malformed entry - skip
                continue
        return out
