# chuk_tool_processor/plugins/xml_tool.py
"""XML tool-call parser plugin.
Understands `<tool name="..." args='{"x":1}'/>` single-line constructs –
format used by many examples and test-fixtures.
"""
from __future__ import annotations

import json
import re
from typing import List
from pydantic import ValidationError

# imports
from .base import ParserPlugin
from chuk_tool_processor.models.tool_call import ToolCall



class XmlToolPlugin(ParserPlugin):
    """Parse XML-like tool-call tags."""

    _TAG = re.compile(
        r"<tool\s+"
        r"name=(?P<q1>[\"\'])(?P<tool>.+?)(?P=q1)\s+"
        r"args=(?P<q2>[\"\'])(?P<args>.*?)(?P=q2)\s*/>"
    )

    def try_parse(self, raw):  # type: ignore[override]
        if not isinstance(raw, str):  # XML form only exists in strings
            return []

        calls: List[ToolCall] = []
        for m in self._TAG.finditer(raw):
            tool_name = m.group("tool")
            raw_args = m.group("args")
            try:
                args = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError:
                args = {}

            try:
                calls.append(ToolCall(tool=tool_name, arguments=args))
            except ValidationError:
                continue  # skip malformed
        return calls
