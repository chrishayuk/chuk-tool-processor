#!/usr/bin/env python
"""
Schema Helper Demo - Typed Tool Args → Schema Export

Demonstrates automatic schema generation from typed tool classes and functions.
One source of truth for validation + discovery - no manual schema writing!

Run this:
    python examples/schema_helper_demo.py
"""

import asyncio
import json
from pydantic import BaseModel, Field

from chuk_tool_processor.models.validated_tool import ValidatedTool
from chuk_tool_processor.models import ToolSpec, ToolCapability, tool_spec
from chuk_tool_processor import register_tool


# --------------------------------------------------------------
# Example 1: ValidatedTool → Automatic Schema Generation
# --------------------------------------------------------------
@register_tool(name="weather")
class WeatherTool(ValidatedTool):
    """Get current weather for a location."""

    class Arguments(BaseModel):
        location: str = Field(..., description="City name or coordinates")
        units: str = Field("celsius", description="Temperature units (celsius/fahrenheit)")
        include_forecast: bool = Field(False, description="Include 7-day forecast")

    class Result(BaseModel):
        temperature: float = Field(..., description="Current temperature")
        conditions: str = Field(..., description="Weather conditions")
        humidity: int = Field(..., description="Humidity percentage")

    async def _execute(self, location: str, units: str, include_forecast: bool) -> Result:
        """Execute weather lookup."""
        return self.Result(
            temperature=22.5 if units == "celsius" else 72.5,
            conditions="Sunny",
            humidity=65
        )


# --------------------------------------------------------------
# Example 2: Enhanced Tool with Metadata
# --------------------------------------------------------------
@tool_spec(
    version="2.1.0",
    capabilities=[ToolCapability.CACHEABLE, ToolCapability.IDEMPOTENT],
    tags=["search", "web", "api"],
    estimated_duration_seconds=2.0,
)
@register_tool(name="search")
class SearchTool(ValidatedTool):
    """Search the web for information."""

    class Arguments(BaseModel):
        query: str = Field(..., description="Search query")
        limit: int = Field(10, description="Maximum results to return", ge=1, le=100)
        filter: str | None = Field(None, description="Optional filter expression")

    class Result(BaseModel):
        results: list[dict] = Field(..., description="Search results")
        total: int = Field(..., description="Total matching results")

    async def _execute(self, query: str, limit: int, filter: str | None) -> Result:
        """Execute search."""
        # Simulate search
        return self.Result(
            results=[{"title": f"Result for: {query}", "url": "https://example.com"}],
            total=100
        )


# --------------------------------------------------------------
# Example 3: Plain Function → Schema Generation
# --------------------------------------------------------------
def calculate(operation: str, a: float, b: float) -> float:
    """Perform a mathematical operation on two numbers."""
    ops = {"add": a + b, "subtract": a - b, "multiply": a * b, "divide": a / b}
    return ops.get(operation, 0.0)


# --------------------------------------------------------------
# Demo
# --------------------------------------------------------------
async def main():
    print("=" * 70)
    print("Schema Helper Demo: Typed Tool Args → Schema Export")
    print("=" * 70)
    print()

    # ------------------------------------------------------------------
    # Example 1: Generate schema from ValidatedTool
    # ------------------------------------------------------------------
    print("Example 1: ValidatedTool → Auto Schema Generation")
    print("-" * 70)
    print()

    # Generate spec from tool class
    weather_spec = ToolSpec.from_validated_tool(WeatherTool, name="weather")

    print("Tool metadata:")
    print(f"  Name: {weather_spec.name}")
    print(f"  Version: {weather_spec.version}")
    print(f"  Description: {weather_spec.description}")
    print()

    print("Generated JSON Schema (parameters):")
    print(json.dumps(weather_spec.parameters, indent=2))
    print()

    # ------------------------------------------------------------------
    # Example 2: Export to different formats
    # ------------------------------------------------------------------
    print("Example 2: Export to LLM-Specific Formats")
    print("-" * 70)
    print()

    # OpenAI format
    print("OpenAI Function Calling format:")
    openai_format = weather_spec.to_openai()
    print(json.dumps(openai_format, indent=2))
    print()

    # Anthropic format
    print("Anthropic Tools format:")
    anthropic_format = weather_spec.to_anthropic()
    print(json.dumps(anthropic_format, indent=2))
    print()

    # MCP format
    print("MCP Tool format:")
    mcp_format = weather_spec.to_mcp()
    print(json.dumps(mcp_format, indent=2))
    print()

    # ------------------------------------------------------------------
    # Example 3: Tool with rich metadata
    # ------------------------------------------------------------------
    print("Example 3: Tool with Rich Metadata")
    print("-" * 70)
    print()

    search_spec = ToolSpec.from_validated_tool(SearchTool, name="search")

    # Access metadata from @tool_spec decorator
    print(f"Version: {search_spec.version}")
    print(f"Capabilities: {search_spec.capabilities}")
    print(f"Tags: {search_spec.tags}")
    print(f"Estimated duration: {search_spec.estimated_duration_seconds}s")
    print()

    # Capability checks
    print("Capability checks:")
    print(f"  Is cacheable? {search_spec.is_cacheable()}")
    print(f"  Is idempotent? {search_spec.is_idempotent()}")
    print(f"  Is streaming? {search_spec.is_streaming()}")
    print()

    # ------------------------------------------------------------------
    # Example 4: Generate schema from plain function
    # ------------------------------------------------------------------
    print("Example 4: Plain Function → Schema Generation")
    print("-" * 70)
    print()

    calc_spec = ToolSpec.from_function(
        calculate,
        name="calculator",
        description="Perform mathematical operations"
    )

    print("Function signature → JSON Schema:")
    print(json.dumps(calc_spec.parameters, indent=2))
    print()

    print("Export to OpenAI:")
    print(json.dumps(calc_spec.to_openai(), indent=2))
    print()

    # ------------------------------------------------------------------
    # Example 5: Use in LLM system prompts
    # ------------------------------------------------------------------
    print("Example 5: Generate LLM System Prompt")
    print("-" * 70)
    print()

    tools = [weather_spec, search_spec, calc_spec]

    print("System prompt with tool definitions:")
    print()
    print("You have access to the following tools:")
    print()

    for tool in tools:
        print(f"Tool: {tool.name}")
        print(f"Description: {tool.description}")
        print(f"Parameters: {json.dumps(tool.parameters, indent=2)}")
        print()

    # ------------------------------------------------------------------
    # Example 6: Complete tool spec export
    # ------------------------------------------------------------------
    print("Example 6: Complete Tool Spec Export")
    print("-" * 70)
    print()

    complete_spec = search_spec.to_dict()
    print("Full tool specification:")
    print(json.dumps(complete_spec, indent=2))
    print()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("=" * 70)
    print("Key Benefits")
    print("=" * 70)
    print()
    print("✅ One Source of Truth:")
    print("   - Define arguments/results once with Pydantic")
    print("   - Automatic schema generation")
    print("   - No manual schema writing")
    print()
    print("✅ Multi-Format Export:")
    print("   - OpenAI function calling")
    print("   - Anthropic tools")
    print("   - MCP tool schema")
    print("   - Pure JSON Schema")
    print()
    print("✅ Rich Metadata:")
    print("   - Version tracking")
    print("   - Capability discovery")
    print("   - Tags and categorization")
    print("   - Execution hints (duration, retries)")
    print()
    print("✅ Type Safety:")
    print("   - Pydantic validation at runtime")
    print("   - IDE autocomplete")
    print("   - LLM gets structured schema")
    print()
    print("Use Cases:")
    print("  • Generate tool definitions for LLM system prompts")
    print("  • Document APIs automatically")
    print("  • Validate tool contracts")
    print("  • Cross-platform tool sharing")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
