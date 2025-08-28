# chuk_tool_processor/plugins/parsers/function_call_tool.py
"""Async parser for OpenAI-style single `function_call` objects."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.plugins.parsers.base import ParserPlugin

__all__ = ["FunctionCallPlugin"]

logger = get_logger(__name__)

# One-level balanced JSON object (good enough for embedded argument blocks)
_JSON_OBJECT = re.compile(r"\{(?:[^{}]|(?:\{[^{}]*\}))*\}")


class PluginMeta:
    """Optional self-description used by the plugin-discovery system (if present)."""

    name: str = "function_call"
    description: str = (
        "Parses a single OpenAI-style `function_call` JSON object (including strings that embed such an object)."
    )
    version: str = "1.0.0"
    author: str = "chuk_tool_processor"


class FunctionCallPlugin(ParserPlugin):
    """Parse messages containing a *single* `function_call` entry."""

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    async def try_parse(self, raw: Any) -> list[ToolCall]:
        # Handle non-string, non-dict inputs gracefully
        if not isinstance(raw, str | dict):
            return []

        payload: dict[str, Any] | None

        # 1️⃣  Primary path ─ whole payload is JSON
        if isinstance(raw, dict):
            payload = raw
        elif isinstance(raw, str):
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = None
        else:
            return []

        calls: list[ToolCall] = []

        if isinstance(payload, dict):
            calls.extend(self._extract_from_payload(payload))

        # 2️⃣  Fallback path ─ scan for *nested* JSON objects inside a string
        if not calls and isinstance(raw, str):
            for match in _JSON_OBJECT.finditer(raw):
                try:
                    sub = json.loads(match.group(0))
                except json.JSONDecodeError:
                    continue
                calls.extend(self._extract_from_payload(sub))

        return calls

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _extract_from_payload(self, payload: dict[str, Any]) -> list[ToolCall]:
        fc = payload.get("function_call")
        if not isinstance(fc, dict):
            return []

        name = fc.get("name")
        args = fc.get("arguments", {})

        # Arguments may themselves be JSON in *string* form
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}

        if not isinstance(args, dict):
            args = {}

        if not isinstance(name, str) or not name:
            return []

        try:
            return [ToolCall(tool=name, arguments=args)]
        except ValidationError:
            logger.debug("Validation error while building ToolCall for %s", name)
            return []
