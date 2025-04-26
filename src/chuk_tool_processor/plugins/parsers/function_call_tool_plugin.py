# chuk_tool_processor/plugins/function_call_tool_plugin.py
"""Function-call parser plugin.
* Accepts dict **or** string input.
* Coerces non-dict `arguments` to `{}` instead of rejecting.
* Inherits from ``ParserPlugin`` so discovery categorises it as a *parser*.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List
from pydantic import ValidationError

# imports
from .base import ParserPlugin
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.logging import get_logger

# logger
logger = get_logger("chuk_tool_processor.plugins.function_call_tool")

# balanced‐brace JSON object regex – one level only (good enough for payloads)
_JSON_OBJECT = re.compile(r"\{(?:[^{}]|(?:\{[^{}]*\}))*\}")


class FunctionCallPlugin(ParserPlugin):
    """Parse OpenAI-style **single** ``function_call`` objects."""

    def try_parse(self, raw: str | Dict[str, Any]) -> List[ToolCall]:
        payload: Dict[str, Any] | None
        if isinstance(raw, dict):
            payload = raw
        else:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = None

        calls: List[ToolCall] = []

        # primary path -----------------------------------------------------
        if isinstance(payload, dict):
            calls.extend(self._extract_from_payload(payload))

        # fallback – scan raw text for nested JSON blocks ------------------
        if not calls and isinstance(raw, str):
            for m in _JSON_OBJECT.finditer(raw):
                try:
                    sub = json.loads(m.group(0))
                except json.JSONDecodeError:
                    continue
                calls.extend(self._extract_from_payload(sub))

        return calls

    # ------------------------------------------------------------------
    def _extract_from_payload(self, payload: Dict[str, Any]) -> List[ToolCall]:
        fc = payload.get("function_call")
        if not isinstance(fc, dict):
            return []

        name = fc.get("name")
        args = fc.get("arguments", {})

        # arguments may be JSON‑encoded string or anything else
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
