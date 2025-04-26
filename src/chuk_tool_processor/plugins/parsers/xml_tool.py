# chuk_tool_processor/plugins/xml_tool.py
import re
import json
from typing import List
from pydantic import ValidationError

# tool processor
from chuk_tool_processor.models.tool_call import ToolCall

class XmlToolPlugin:
    """
    Parse XML-like `<tool name="..." args='{"x":1}'/>` constructs,
    supporting both single- and double-quoted attributes.
    """
    _pattern = re.compile(
        r'<tool\s+'
        r'name=(?P<q1>["\'])(?P<tool>.+?)(?P=q1)\s+'
        r'args=(?P<q2>["\'])(?P<args>.*?)(?P=q2)\s*/>'
    )

    def try_parse(self, raw: str) -> List[ToolCall]:
        calls: List[ToolCall] = []
        for m in self._pattern.finditer(raw):
            tool_name = m.group('tool')
            raw_args = m.group('args')
            # Decode the JSON payload in the args attribute
            try:
                args = json.loads(raw_args) if raw_args else {}
            except (json.JSONDecodeError, ValidationError):
                args = {}

            # Validate & construct the ToolCall
            try:
                call = ToolCall(tool=tool_name, arguments=args)
                calls.append(call)
            except ValidationError:
                # Skip malformed calls
                continue

        return calls

