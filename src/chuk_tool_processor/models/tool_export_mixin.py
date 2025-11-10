# chuk_tool_processor/models/tool_export_mix_in.py

from typing import Any, Protocol, cast, runtime_checkable

from pydantic import BaseModel


@runtime_checkable
class HasArguments(Protocol):
    """Protocol for classes that have an Arguments attribute."""

    Arguments: type[BaseModel]


class ToolExportMixin:
    """Mixin that lets any ValidatedTool advertise its schema."""

    @classmethod
    def to_openai(cls) -> dict[str, Any]:
        assert hasattr(cls, "Arguments"), f"{cls.__name__} must have an Arguments attribute"
        schema = cls.Arguments.model_json_schema()  # noqa: ANN401
        return {
            "type": "function",
            "function": {
                "name": cls.__name__.removesuffix("Tool").lower(),  # or keep explicit name
                "description": (cls.__doc__ or "").strip(),
                "parameters": schema,
            },
        }

    @classmethod
    def to_json_schema(cls) -> dict[str, Any]:
        assert hasattr(cls, "Arguments"), f"{cls.__name__} must have an Arguments attribute"
        return cast(dict[str, Any], cls.Arguments.model_json_schema())

    @classmethod
    def to_xml(cls) -> str:
        """Very small helper so existing XML-based parsers still work."""
        assert hasattr(cls, "Arguments"), f"{cls.__name__} must have an Arguments attribute"
        name = cls.__name__.removesuffix("Tool").lower()
        params = cls.Arguments.model_json_schema()["properties"]  # noqa: ANN401
        args = ", ".join(params)
        return f'<tool name="{name}" args="{{{args}}}"/>'
