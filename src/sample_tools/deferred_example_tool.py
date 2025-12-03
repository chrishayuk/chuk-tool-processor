# sample_tools/deferred_example_tool.py
"""
Example deferred tools to demonstrate dynamic tool loading.

These tools are marked with defer_loading=True, so they won't be loaded
until explicitly requested via tool_search or direct access.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from chuk_tool_processor.models.validated_tool import ValidatedTool
from chuk_tool_processor.registry import register_tool


@register_tool(
    namespace="data",
    defer_loading=True,
    search_keywords=["csv", "comma-separated", "data", "parse"],
    tags={"data", "csv", "parser"},
)
class CSVParserTool(ValidatedTool):
    """
    Parse CSV data and return structured results.

    This is a deferred tool - it won't be loaded until requested.
    """

    class Arguments(BaseModel):
        csv_data: str = Field(..., description="CSV data to parse")
        delimiter: str = Field(",", description="Column delimiter (default: comma)")
        has_header: bool = Field(True, description="Whether first row is header")

    class Result(BaseModel):
        rows: list[dict[str, str]] = Field(..., description="Parsed rows as dicts")
        row_count: int = Field(..., description="Number of rows parsed")

    async def _execute(
        self,
        csv_data: str,
        delimiter: str = ",",
        has_header: bool = True,
    ) -> dict:
        """Parse CSV data."""
        lines = csv_data.strip().split("\n")

        if not lines:
            return {"rows": [], "row_count": 0}

        # Parse header
        header = None
        start_idx = 0
        if has_header:
            header = lines[0].split(delimiter)
            start_idx = 1

        # Parse rows
        rows = []
        for line in lines[start_idx:]:
            values = line.split(delimiter)
            row = dict(zip(header, values, strict=False)) if header else {f"col_{i}": v for i, v in enumerate(values)}
            rows.append(row)

        return {
            "rows": rows,
            "row_count": len(rows),
        }


@register_tool(
    namespace="data",
    defer_loading=True,
    search_keywords=["json", "parse", "data", "serialize"],
    tags={"data", "json", "parser"},
)
class JSONValidatorTool(ValidatedTool):
    """
    Validate and pretty-print JSON data.

    This is a deferred tool - it won't be loaded until requested.
    """

    class Arguments(BaseModel):
        json_data: str = Field(..., description="JSON data to validate")
        strict: bool = Field(True, description="Use strict JSON parsing")

    class Result(BaseModel):
        valid: bool = Field(..., description="Whether JSON is valid")
        pretty: str | None = Field(None, description="Pretty-printed JSON if valid")
        error: str | None = Field(None, description="Error message if invalid")

    async def _execute(self, json_data: str, strict: bool = True) -> dict:
        """Validate JSON data."""
        import json

        try:
            parsed = json.loads(json_data, strict=strict)
            pretty = json.dumps(parsed, indent=2, sort_keys=True)
            return {
                "valid": True,
                "pretty": pretty,
                "error": None,
            }
        except json.JSONDecodeError as e:
            return {
                "valid": False,
                "pretty": None,
                "error": str(e),
            }


@register_tool(
    namespace="ml",
    defer_loading=True,
    search_keywords=["machine learning", "model", "train", "predict"],
    tags={"ml", "ai", "model"},
)
class SimpleMLTool(ValidatedTool):
    """
    Simple machine learning operations (mock implementation).

    This is a deferred tool in the 'ml' namespace.
    """

    class Arguments(BaseModel):
        operation: str = Field(..., description="Operation: 'train' or 'predict'")
        data: list[float] = Field(..., description="Input data")

    class Result(BaseModel):
        result: float | str = Field(..., description="Operation result")
        operation: str = Field(..., description="Operation performed")

    async def _execute(self, operation: str, data: list[float]) -> dict:
        """Perform ML operation (mock)."""
        if operation == "train":
            # Mock: return "accuracy"
            return {
                "result": 0.95,
                "operation": "train",
            }
        elif operation == "predict":
            # Mock: return mean
            return {
                "result": sum(data) / len(data) if data else 0.0,
                "operation": "predict",
            }
        else:
            return {
                "result": f"Unknown operation: {operation}",
                "operation": operation,
            }
