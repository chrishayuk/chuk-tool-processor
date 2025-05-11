# chuk_tool_processor/plugins/function_call_tool_plugin.py
"""Async parser for OpenAI-style single `function_call` objects."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from pydantic import ValidationError

from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.models.tool_call import ToolCall
from .base import ParserPlugin

logger = get_logger(__name__)

# One-level balanced JSON object (good enough for embedded argument blocks)
_JSON_OBJECT = re.compile(r"\{(?:[^{}]|(?:\{[^{}]*\}))*\}")


class FunctionCallPlugin(ParserPlugin):
    """Parse messages containing a *single* `function_call` entry."""

    async def try_parse(self, raw: str | Dict[str, Any]) -> List[ToolCall]:
        payload: Dict[str, Any] | None

        # ------------------------------------------------------------------
        # 1. Primary: whole payload is JSON
        # ------------------------------------------------------------------
        if isinstance(raw, dict):
            payload = raw
        else:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = None

        calls: List[ToolCall] = []

        if isinstance(payload, dict):
            calls.extend(self._extract_from_payload(payload))

        # ------------------------------------------------------------------
        # 2. Fallback: scan string for nested JSON objects
        # ------------------------------------------------------------------
        if not calls and isinstance(raw, str):
            for m in _JSON_OBJECT.finditer(raw):
                try:
                    sub = json.loads(m.group(0))
                except json.JSONDecodeError:
                    continue
                calls.extend(self._extract_from_payload(sub))

        return calls

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _extract_from_payload(self, payload: Dict[str, Any]) -> List[ToolCall]:
        fc = payload.get("function_call")
        if not isinstance(fc, dict):
            return []

        name = fc.get("name")
        args = fc.get("arguments", {})

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
