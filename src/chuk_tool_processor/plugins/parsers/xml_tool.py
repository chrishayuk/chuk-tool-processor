# chuk_tool_processor/plugins/parsers/xml_tool.py
"""
Async-native parser for single-line XML-style tool-call tags, e.g.

    <tool name="translate" args="{\"text\": \"Hello\", \"target\": \"es\"}"/>

The *args* attribute may be

1. A proper JSON object:                   args="{"x": 1}"
2. A JSON-encoded string (most common):    args="{\"x\": 1}"
3. The empty string:                       args=""

All variants are normalised to a **dict** of arguments.
"""

from __future__ import annotations

import json
import re
from typing import List

from pydantic import ValidationError

from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.plugins.parsers.base import ParserPlugin

__all__: list[str] = ["XmlToolPlugin"]

logger = get_logger(__name__)


class PluginMeta:
    """Optional descriptor that can be used by the plugin-discovery mechanism."""
    name: str = "xml_tool_tag"
    description: str = "Parses <tool …/> XML tags into ToolCall objects."
    version: str = "1.0.0"
    author: str = "chuk_tool_processor"


class XmlToolPlugin(ParserPlugin):
    """Convert `<tool …/>` tags into :class:`ToolCall` objects."""

    _TAG = re.compile(
        r"<tool\s+"
        r"name=(?P<q1>[\"'])(?P<tool>.+?)(?P=q1)\s+"
        r"args=(?P<q2>[\"'])(?P<args>.*?)(?P=q2)\s*/>",
        flags=re.IGNORECASE | re.DOTALL,
    )

    # ------------------------------------------------------------------ #
    async def try_parse(self, raw: str | object) -> List[ToolCall]:  # noqa: D401
        if not isinstance(raw, str):
            return []

        calls: List[ToolCall] = []

        for match in self._TAG.finditer(raw):
            name = match.group("tool")
            raw_args = match.group("args") or ""
            args = self._decode_args(raw_args)

            try:
                calls.append(ToolCall(tool=name, arguments=args))
            except ValidationError:
                logger.debug("xml_tool_plugin: validation error for <%s>", name)

        return calls

    # ------------------------------------------------------------------ #
    # Helper – robust JSON decode for the args attribute
    # ------------------------------------------------------------------ #
    @staticmethod
    def _decode_args(raw_args: str) -> dict:
        """Best-effort decoding of the *args* attribute to a dict."""
        if not raw_args:
            return {}

        # 1️⃣ Try direct JSON
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError:
            parsed = None

        # 2️⃣ If still None, the value might be a JSON-encoded string
        if parsed is None:
            try:
                parsed = json.loads(raw_args.encode().decode("unicode_escape"))
            except json.JSONDecodeError:
                parsed = None

        # 3️⃣ Last resort – naive unescaping of \" → "
        if parsed is None:
            try:
                parsed = json.loads(raw_args.replace(r"\"", "\""))
            except json.JSONDecodeError:
                parsed = {}

        return parsed if isinstance(parsed, dict) else {}
