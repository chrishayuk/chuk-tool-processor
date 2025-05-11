# chuk_tool_processor/plugins/parsers/xml_tool.py
"""
Async parser for single-line XML-style tool-call tags:

    <tool name="translate" args="{\"text\": \"Hello\", \"target\": \"es\"}"/>

The `args` attribute may be:

* a *proper* JSON object:                   args="{"x": 1}"
* a *JSON-encoded* **string** (common):     args="{\"x\": 1}"
* the empty string:                         args=""

All are handled and normalised to a **dict**.
"""
from __future__ import annotations

import json
import re
from typing import List

from pydantic import ValidationError

from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.plugins.parsers.base import ParserPlugin

# --------------------------------------------------------------------------- #
class XmlToolPlugin(ParserPlugin):
    """Parse `<tool …/>` constructs into :class:`ToolCall` objects."""

    _TAG = re.compile(
        r"<tool\s+"
        r"name=(?P<q1>[\"'])(?P<tool>.+?)(?P=q1)\s+"
        r"args=(?P<q2>[\"'])(?P<args>.*?)(?P=q2)\s*/>"
    )

    # ------------------------------------------------------------------ #
    async def try_parse(self, raw):  # type: ignore[override]
        if not isinstance(raw, str):
            return []

        calls: List[ToolCall] = []

        for m in self._TAG.finditer(raw):
            name = m.group("tool")
            raw_args = m.group("args") or ""

            args = self._decode_args(raw_args)

            try:
                calls.append(ToolCall(tool=name, arguments=args))
            except ValidationError:
                continue  # skip malformed entries

        return calls

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _decode_args(raw_args: str) -> dict:
        """Return a dict from the raw *args* attribute (best-effort)."""
        if not raw_args:
            return {}

        # 1. direct JSON
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError:
            parsed = None

        # 2. maybe the value itself is a JSON-encoded string
        if parsed is None:
            try:
                parsed = json.loads(
                    raw_args.encode("utf-8").decode("unicode_escape")
                )
            except json.JSONDecodeError:
                parsed = None

        # 3. last chance: naive unescape of \" → "
        if parsed is None:
            try:
                parsed = json.loads(raw_args.replace(r"\"\"", "\""))
            except json.JSONDecodeError:
                parsed = {}

        return parsed if isinstance(parsed, dict) else {}
