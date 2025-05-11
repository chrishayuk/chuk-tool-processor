# tests/tool_processor/plugins/parsers/test_function_call_tool.py
"""
Async parser for an OpenAI-style **single** ``function_call`` object.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from pydantic import ValidationError

from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.plugins.parsers.base import ParserPlugin

logger = get_logger(__name__)

# One-level balanced JSON object — enough for argument blocks embedded in text.
_JSON_OBJECT = re.compile(r"\{(?:[^{}]|(?:\{[^{}]*\}))*\}")


class FunctionCallPlugin(ParserPlugin):
    """Parse strings or dicts that contain exactly one ``function_call`` entry."""

    async def try_parse(self, raw: str | Dict[str, Any]) -> List[ToolCall]:  # noqa: D401
        payload: Dict[str, Any] | None

        # ──────────────────────────────────────────────────────────
        # 1) primary path — whole payload is (or parses as) JSON
        # ──────────────────────────────────────────────────────────
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

        # ──────────────────────────────────────────────────────────
        # 2) fallback — scan text for nested JSON objects
        # ──────────────────────────────────────────────────────────
        if not calls and isinstance(raw, str):
            for match in _JSON_OBJECT.finditer(raw):
                try:
                    sub = json.loads(match.group(0))
                except json.JSONDecodeError:
                    continue
                calls.extend(self._extract_from_payload(sub))

        return calls

    # ------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------
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
        except ValidationError:  # pragma: no cover — invalid schema → skip
            logger.debug("Validation error while building ToolCall (%s)", name)
            return []
