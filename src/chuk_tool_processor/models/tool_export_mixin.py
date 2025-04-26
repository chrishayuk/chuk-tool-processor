# chuk_tool_processor/models/tool_export_mix_in.py
from typing import Dict

class ToolExportMixin:
    """Mixin that lets any ValidatedTool advertise its schema."""

    @classmethod
    def to_openai(cls) -> Dict:
        schema = cls.Arguments.model_json_schema()
        return {
            "type": "function",
            "function": {
                "name": cls.__name__.removesuffix("Tool").lower(),   # or keep explicit name
                "description": (cls.__doc__ or "").strip(),
                "parameters": schema,
            },
        }

    @classmethod
    def to_json_schema(cls) -> Dict:
        return cls.Arguments.model_json_schema()

    @classmethod
    def to_xml(cls) -> str:
        """Very small helper so existing XML-based parsers still work."""
        name = cls.__name__.removesuffix("Tool").lower()
        params = cls.Arguments.model_json_schema()["properties"]
        args = ", ".join(params)
        return f"<tool name=\"{name}\" args=\"{{{args}}}\"/>"
