#!/usr/bin/env python3
"""
Working Deferred Loading Example

This example actually demonstrates deferred loading in action with real tools.
"""

import asyncio

from pydantic import BaseModel, Field

from chuk_tool_processor.models.validated_tool import ValidatedTool
from chuk_tool_processor.registry import get_default_registry, register_tool, reset_registry


# ============================================================================
# CORE TOOLS (Always loaded)
# ============================================================================


@register_tool(namespace="core")
class CalculatorTool(ValidatedTool):
    """Basic calculator - always available."""

    class Arguments(BaseModel):
        operation: str = Field(..., description="Operation: add, subtract, multiply, divide")
        a: float = Field(..., description="First number")
        b: float = Field(..., description="Second number")

    class Result(BaseModel):
        result: float = Field(..., description="Calculation result")

    async def _execute(self, operation: str, a: float, b: float) -> dict:
        ops = {
            "add": a + b,
            "subtract": a - b,
            "multiply": a * b,
            "divide": a / b if b != 0 else float('inf')
        }
        return {"result": ops.get(operation, 0)}


# ============================================================================
# DEFERRED TOOLS (Loaded on-demand)
# ============================================================================


@register_tool(
    namespace="data",
    defer_loading=True,
    search_keywords=["csv", "comma-separated", "parse", "data"],
    tags={"data", "csv", "parser"},
)
class CSVParserTool(ValidatedTool):
    """Parse CSV data - loaded on demand."""

    class Arguments(BaseModel):
        csv_data: str = Field(..., description="CSV data to parse")

    class Result(BaseModel):
        rows: list = Field(..., description="Parsed rows")
        count: int = Field(..., description="Number of rows")

    async def _execute(self, csv_data: str) -> dict:
        lines = csv_data.strip().split("\n")
        header = lines[0].split(",")
        rows = []
        for line in lines[1:]:
            values = line.split(",")
            rows.append(dict(zip(header, values)))
        return {"rows": rows, "count": len(rows)}


@register_tool(
    namespace="data",
    defer_loading=True,
    search_keywords=["json", "validate", "parse"],
    tags={"data", "json"},
)
class JSONValidatorTool(ValidatedTool):
    """Validate JSON - loaded on demand."""

    class Arguments(BaseModel):
        json_str: str = Field(..., description="JSON string to validate")

    class Result(BaseModel):
        valid: bool = Field(..., description="Whether JSON is valid")
        error: str | None = Field(None, description="Error message if invalid")

    async def _execute(self, json_str: str) -> dict:
        import json
        try:
            json.loads(json_str)
            return {"valid": True, "error": None}
        except json.JSONDecodeError as e:
            return {"valid": False, "error": str(e)}


@register_tool(
    namespace="ml",
    defer_loading=True,
    search_keywords=["machine learning", "predict", "model", "inference"],
    tags={"ml", "ai"},
)
class MLPredictTool(ValidatedTool):
    """ML prediction - loaded on demand."""

    class Arguments(BaseModel):
        model_name: str = Field(..., description="Model to use")
        features: list[float] = Field(..., description="Input features")

    class Result(BaseModel):
        prediction: float = Field(..., description="Model prediction")

    async def _execute(self, model_name: str, features: list[float]) -> dict:
        # Mock prediction: return average of features
        return {"prediction": sum(features) / len(features) if features else 0.0}


# ============================================================================
# DEMONSTRATION
# ============================================================================


async def demonstrate():
    """Demonstrate deferred loading in action."""
    print("=" * 80)
    print("WORKING DEFERRED LOADING DEMONSTRATION")
    print("=" * 80)
    print()

    # Reset registry to start clean
    await reset_registry()

    # Initialize registry (this processes @register_tool decorators)
    registry = await get_default_registry()

    # ========================================================================
    # STEP 1: Show initial state
    # ========================================================================
    print("STEP 1: Initial Registry State")
    print("-" * 80)

    active_tools = await registry.get_active_tools()
    deferred_tools = await registry.get_deferred_tools()

    print(f"\n✅ Active tools (loaded): {len(active_tools)}")
    for tool in active_tools:
        metadata = await registry.get_metadata(tool.name, tool.namespace)
        print(f"   • {tool.namespace}:{tool.name} - {metadata.description}")

    print(f"\n✅ Deferred tools (NOT loaded yet): {len(deferred_tools)}")
    for tool in deferred_tools:
        metadata = await registry.get_metadata(tool.name, tool.namespace)
        print(f"   • {tool.namespace}:{tool.name} - {metadata.description}")

    print()

    # ========================================================================
    # STEP 2: Search for tools
    # ========================================================================
    print("STEP 2: Searching for Tools")
    print("-" * 80)

    print("\nSearching for 'csv' tools...")
    csv_results = await registry.search_deferred_tools(query="csv parse", limit=3)

    if csv_results:
        print(f"✅ Found {len(csv_results)} matching tools:")
        for tool_meta in csv_results:
            print(f"   • {tool_meta.name}")
            print(f"     - Description: {tool_meta.description}")
            print(f"     - Keywords: {', '.join(tool_meta.search_keywords)}")
    else:
        print("   (No results)")

    print()

    # ========================================================================
    # STEP 3: Load a deferred tool on-demand
    # ========================================================================
    print("STEP 3: Loading Tool On-Demand")
    print("-" * 80)

    print("\nLoading CSVParserTool...")
    csv_tool = await registry.load_deferred_tool("CSVParserTool", "data")
    print(f"✅ Loaded: {csv_tool}")

    # Verify it's now active
    active_after = await registry.get_active_tools()
    deferred_after = await registry.get_deferred_tools()

    print(f"\n✅ Active tools now: {len(active_after)} (was {len(active_tools)})")
    print(f"✅ Deferred tools now: {len(deferred_after)} (was {len(deferred_tools)})")

    print()

    # ========================================================================
    # STEP 4: Actually use the tool!
    # ========================================================================
    print("STEP 4: Using the Loaded Tool")
    print("-" * 80)

    print("\nParsing CSV data...")
    csv_data = """name,age,city
Alice,30,NYC
Bob,25,LA
Charlie,35,Chicago"""

    csv_tool_instance = csv_tool()
    result = await csv_tool_instance.execute(csv_data=csv_data)
    result_dict = result.model_dump()

    print(f"✅ Parsed {result_dict['count']} rows:")
    for i, row in enumerate(result_dict['rows'], 1):
        print(f"   {i}. {row}")

    print()

    # ========================================================================
    # STEP 5: Load multiple tools dynamically
    # ========================================================================
    print("STEP 5: Loading Multiple Tools Dynamically")
    print("-" * 80)

    print("\nSearching for 'json' tools...")
    json_results = await registry.search_deferred_tools(query="json", limit=2)
    for tool_meta in json_results:
        print(f"   Loading {tool_meta.name}...")
        await registry.load_deferred_tool(tool_meta.name, tool_meta.namespace)

    print("\nSearching for 'machine learning' tools...")
    ml_results = await registry.search_deferred_tools(query="machine learning", limit=2)
    for tool_meta in ml_results:
        print(f"   Loading {tool_meta.name}...")
        await registry.load_deferred_tool(tool_meta.name, tool_meta.namespace)

    # Show final state
    active_final = await registry.get_active_tools()
    deferred_final = await registry.get_deferred_tools()

    print(f"\n✅ Final state:")
    print(f"   Active: {len(active_final)} tools")
    print(f"   Deferred: {len(deferred_final)} tools")

    print()

    # ========================================================================
    # STEP 6: The Value Proposition
    # ========================================================================
    print("STEP 6: API Binding Simulation")
    print("-" * 80)

    print("\nSimulating LLM API calls...\n")

    # API Call 1: Initial
    print("API Call #1 (Initial):")
    tools_for_api_1 = [t for t in active_tools if not t.name.startswith("Tool")]
    print(f"   Tools sent: {[f'{t.namespace}:{t.name}' for t in tools_for_api_1]}")
    print(f"   Count: {len(tools_for_api_1)} tools")

    # User asks about CSV
    print("\nUser: 'Parse this CSV data...'")
    print("Claude: I need CSV tools!")
    print("→ Searches and loads CSVParserTool")

    # API Call 2: With CSV tool
    print("\nAPI Call #2 (After search):")
    tools_for_api_2 = [t for t in active_final if not t.name.startswith("Tool")]
    print(f"   Tools sent: {[f'{t.namespace}:{t.name}' for t in tools_for_api_2]}")
    print(f"   Count: {len(tools_for_api_2)} tools")

    print("\n✅ Dynamic tool binding in action!")
    print("   • Started with 1 tool")
    print(f"   • Grew to {len(tools_for_api_2)} tools")
    print("   • All under the 128 function limit!")

    print()
    print("=" * 80)
    print("DEMONSTRATION COMPLETE")
    print("=" * 80)
    print()
    print("Key Takeaways:")
    print("  1. Tools marked defer_loading=True aren't loaded initially")
    print("  2. search_deferred_tools() finds tools by keywords")
    print("  3. load_deferred_tool() loads them on-demand")
    print("  4. get_active_tools() shows only loaded tools for API binding")
    print("  5. This breaks the 128 function limit!")
    print()


if __name__ == "__main__":
    asyncio.run(demonstrate())
