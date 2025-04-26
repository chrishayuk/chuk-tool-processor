# chuk_tool_processor/plugins/json_tool.py
import json
from typing import List
from pydantic import ValidationError

# tool processor
from chuk_tool_processor.models.tool_call import ToolCall

class JsonToolPlugin:
    """Parse JSON-encoded `tool_calls` field."""
    def try_parse(self, raw: str) -> List[ToolCall]:
        try:
            data = json.loads(raw)
            calls = data.get('tool_calls', []) if isinstance(data, dict) else []
            return [ToolCall(**c) for c in calls]
        except (json.JSONDecodeError, ValidationError):
            return []