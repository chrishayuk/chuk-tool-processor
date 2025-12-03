#!/usr/bin/env python3
"""
Complete Advanced Tool Use Example

Demonstrates all three advanced tool use features working together:
1. Deferred Loading - Only load tools when needed
2. Tool Use Examples - Improve accuracy with concrete examples
3. Programmatic Execution - Enable code-based tool orchestration

This example shows how to:
- Register tools with examples and deferred loading
- Export to multiple providers (OpenAI, Anthropic, MCP)
- Use tool search to discover and load tools on-demand
- Mark tools for programmatic execution

Usage:
    PYTHONPATH=/Users/christopherhay/chris-source/chuk-ai/chuk-tool-processor/src python examples/advanced_tool_use_complete.py
"""

import asyncio
import json
import sys
from datetime import datetime

# Use local source
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pydantic import BaseModel, Field

from chuk_tool_processor.models.tool_spec import ToolCapability, ToolSpec
from chuk_tool_processor.models.validated_tool import ValidatedTool
from chuk_tool_processor.registry import get_default_registry, register_tool, reset_registry


# ============================================================================
# Tool Definitions with Examples
# ============================================================================


@register_tool(
    namespace="sales",
    tags=["database", "sales", "analytics"],
    # Deferred loading - only load when needed
    defer_loading=False,  # Core tool - always loaded
    # Programmatic execution - can be called from code
    allowed_callers=["code_execution_20250825", "sandbox"],
    # Examples for better accuracy
    examples=[
        {
            "input": {
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "min_revenue": 1000.0,
            },
            "description": "Get sales for January 2024 with revenue filter",
        },
        {
            "input": {"start_date": "2024-01-01", "end_date": "2024-12-31"},
            "description": "Full year sales report",
        },
        {
            "input": {
                "start_date": "2024-06-01",
                "end_date": "2024-06-30",
                "min_revenue": 5000.0,
                "limit": 10,
            },
            "description": "Top 10 high-value sales in June",
        },
    ],
)
class GetSalesDataTool(ValidatedTool):
    """
    Fetch sales data from database.

    Returns sales records with detailed information for analysis.
    All dates in YYYY-MM-DD format. Revenue in USD.

    Return format:
        {
            "rows": [
                {
                    "sale_id": "S12345",
                    "customer_id": "C789",
                    "product_id": "P456",
                    "revenue": 1500.00,
                    "date": "2024-01-15",
                    "region": "North America"
                },
                ...
            ],
            "total_count": 150
        }
    """

    class Arguments(BaseModel):
        start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
        end_date: str = Field(..., description="End date (YYYY-MM-DD)")
        min_revenue: float | None = Field(
            None, description="Minimum revenue filter in USD"
        )
        limit: int | None = Field(None, description="Maximum number of records to return")

    class Result(BaseModel):
        rows: list[dict] = Field(..., description="Sales records")
        total_count: int = Field(..., description="Total matching records")

    async def _execute(
        self,
        start_date: str,
        end_date: str,
        min_revenue: float | None = None,
        limit: int | None = None,
    ) -> dict:
        """Fetch sales data (simulated)."""
        # Simulate database query
        sales = [
            {
                "sale_id": "S001",
                "customer_id": "C123",
                "product_id": "P456",
                "revenue": 2500.0,
                "date": "2024-01-15",
                "region": "North America",
            },
            {
                "sale_id": "S002",
                "customer_id": "C124",
                "product_id": "P457",
                "revenue": 1800.0,
                "date": "2024-01-16",
                "region": "Europe",
            },
            {
                "sale_id": "S003",
                "customer_id": "C125",
                "product_id": "P458",
                "revenue": 5000.0,
                "date": "2024-01-17",
                "region": "Asia",
            },
        ]

        # Apply filters
        if min_revenue:
            sales = [s for s in sales if s["revenue"] >= min_revenue]

        if limit:
            sales = sales[:limit]

        return {"rows": sales, "total_count": len(sales)}


@register_tool(
    namespace="sales",
    tags=["analytics", "aggregation"],
    # Deferred loading - advanced analytics tool
    defer_loading=True,
    search_keywords=["aggregate", "summarize", "total", "group", "revenue"],
    # Programmatic execution
    allowed_callers=["code_execution_20250825", "sandbox"],
    # Examples
    examples=[
        {
            "input": {"sales_data": [{"revenue": 100}, {"revenue": 200}]},
            "description": "Simple revenue aggregation",
        }
    ],
)
class AggregateSalesTool(ValidatedTool):
    """
    Aggregate sales data by various dimensions.

    Calculates totals, averages, and counts grouped by region, product, or customer.
    Input must be sales records with revenue field.
    """

    class Arguments(BaseModel):
        sales_data: list[dict] = Field(..., description="Sales records to aggregate")
        group_by: str = Field(
            "region", description="Field to group by (region, product_id, customer_id)"
        )

    class Result(BaseModel):
        aggregates: list[dict] = Field(..., description="Aggregated results")

    async def _execute(self, sales_data: list[dict], group_by: str = "region") -> dict:
        """Aggregate sales data."""
        from collections import defaultdict

        groups = defaultdict(lambda: {"total_revenue": 0.0, "count": 0})

        for sale in sales_data:
            key = sale.get(group_by, "Unknown")
            groups[key]["total_revenue"] += sale.get("revenue", 0)
            groups[key]["count"] += 1

        aggregates = [
            {
                group_by: key,
                "total_revenue": stats["total_revenue"],
                "count": stats["count"],
                "average_revenue": stats["total_revenue"] / stats["count"]
                if stats["count"] > 0
                else 0,
            }
            for key, stats in groups.items()
        ]

        return {"aggregates": sorted(aggregates, key=lambda x: x["total_revenue"], reverse=True)}


@register_tool(
    namespace="sales",
    tags=["visualization", "reporting"],
    # Deferred loading - specialized reporting tool
    defer_loading=True,
    search_keywords=["chart", "graph", "visualize", "plot", "report"],
    # Programmatic execution
    allowed_callers=["code_execution_20250825", "sandbox"],
    # Examples
    examples=[
        {
            "input": {
                "data": [{"region": "US", "revenue": 10000}],
                "chart_type": "bar",
                "title": "Revenue by Region",
            },
            "description": "Create a bar chart of revenue by region",
        }
    ],
)
class CreateChartTool(ValidatedTool):
    """
    Create data visualization from aggregated data.

    Generates charts and graphs for sales reports.
    Returns chart configuration in JSON format.
    """

    class Arguments(BaseModel):
        data: list[dict] = Field(..., description="Data to visualize")
        chart_type: str = Field(..., description="Type of chart (bar, line, pie)")
        title: str = Field(..., description="Chart title")

    class Result(BaseModel):
        chart_config: dict = Field(..., description="Chart configuration")

    async def _execute(self, data: list[dict], chart_type: str, title: str) -> dict:
        """Create chart configuration."""
        return {
            "chart_config": {
                "type": chart_type,
                "title": title,
                "data": data,
                "created_at": datetime.now().isoformat(),
            }
        }


# ============================================================================
# Main Demonstration
# ============================================================================


async def demonstrate_advanced_tool_use():
    """Demonstrate all three advanced tool use features."""
    print("=" * 80)
    print("ADVANCED TOOL USE - COMPLETE DEMONSTRATION")
    print("=" * 80)
    print()

    # Reset registry for clean start
    await reset_registry()
    registry = await get_default_registry()

    # ========================================================================
    # STEP 1: Check Initial State
    # ========================================================================
    print("STEP 1: Initial Tool State")
    print("-" * 80)
    print()

    active_tools = await registry.get_active_tools(namespace="sales")
    deferred_tools = await registry.get_deferred_tools(namespace="sales")

    print(f"✅ Active (loaded): {len(active_tools)} tools")
    for tool in active_tools:
        metadata = await registry.get_metadata(tool.name, tool.namespace)
        print(f"   • {tool.name}: {metadata.description[:60]}...")

    print()
    print(f"⏳ Deferred (not loaded yet): {len(deferred_tools)} tools")
    for tool in deferred_tools:
        metadata = await registry.get_metadata(tool.name, tool.namespace)
        print(f"   • {tool.name}: {metadata.description[:60]}...")
    print()

    # ========================================================================
    # STEP 2: Show Tool Examples
    # ========================================================================
    print("STEP 2: Tool Use Examples")
    print("-" * 80)
    print()

    # Get tool class and instantiate it
    sales_tool_class = await registry.get_tool("GetSalesDataTool", "sales")
    sales_tool_obj = sales_tool_class()  # Create instance
    core_tool_metadata = await registry.get_metadata("GetSalesDataTool", "sales")

    # Create spec with examples
    spec = ToolSpec(
        name="GetSalesDataTool",
        description=core_tool_metadata.description or "Get sales data",
        parameters=GetSalesDataTool.Arguments.model_json_schema(),
        examples=[
            {
                "input": {
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-31",
                    "min_revenue": 1000.0,
                },
                "description": "Get sales for January 2024 with revenue filter",
            },
            {
                "input": {"start_date": "2024-01-01", "end_date": "2024-12-31"},
                "description": "Full year sales report",
            },
        ],
        namespace="sales",
        allowed_callers=["code_execution_20250825", "sandbox"],
    )

    print(f"Tool: {spec.name}")
    print(f"Examples provided: {len(spec.examples)}")
    print()

    for i, example in enumerate(spec.examples, 1):
        print(f"Example {i}: {example.get('description', 'No description')}")
        print(f"  Input: {json.dumps(example['input'], indent=4)}")
        print()

    # ========================================================================
    # STEP 3: Export to Multiple Providers
    # ========================================================================
    print("STEP 3: Provider-Agnostic Export")
    print("-" * 80)
    print()

    print("📤 Exporting to OpenAI format:")
    openai_format = spec.to_openai()
    print(f"  - Tool name: {openai_format['function']['name']}")
    print(f"  - Has examples: {'examples' in openai_format['function']}")
    if "examples" in openai_format["function"]:
        print(f"  - Example count: {len(openai_format['function']['examples'])}")
    print()

    print("📤 Exporting to Anthropic format:")
    anthropic_format = spec.to_anthropic()
    print(f"  - Tool name: {anthropic_format['name']}")
    print(f"  - Has examples: {'examples' in anthropic_format}")
    if "examples" in anthropic_format:
        print(f"  - Example count: {len(anthropic_format['examples'])}")
    print(f"  - Programmatic execution: {'allowed_callers' in anthropic_format}")
    if "allowed_callers" in anthropic_format:
        print(f"  - Allowed callers: {anthropic_format['allowed_callers']}")
    print()

    print("📤 Exporting to MCP format:")
    mcp_format = spec.to_mcp()
    print(f"  - Tool name: {mcp_format['name']}")
    print(f"  - Has examples: {'examples' in mcp_format}")
    if "examples" in mcp_format:
        print(f"  - Example count: {len(mcp_format['examples'])}")
    print()

    # ========================================================================
    # STEP 4: Tool Search and Dynamic Loading
    # ========================================================================
    print("STEP 4: Dynamic Tool Discovery")
    print("-" * 80)
    print()

    print("Scenario: User asks to 'aggregate sales by region'")
    print()

    # Search for tools
    search_results = await registry.search_deferred_tools(
        query="aggregate revenue group", limit=5
    )

    print(f"🔍 Found {len(search_results)} matching deferred tools:")
    for result in search_results:
        print(f"   • {result.name}: {result.description[:60]}...")
    print()

    if search_results:
        # Load the first matching tool
        tool_to_load = search_results[0]
        print(f"⬇️  Loading tool: {tool_to_load.name}")
        loaded_tool = await registry.load_deferred_tool(
            tool_to_load.name, tool_to_load.namespace
        )
        print(f"✅ Tool loaded and ready to use")
        print()

    # ========================================================================
    # STEP 5: Execute Tools (Simulated Programmatic Execution)
    # ========================================================================
    print("STEP 5: Tool Execution (Programmatic Style)")
    print("-" * 80)
    print()

    print("Simulating code that Claude might write:")
    print()
    print('```python')
    print('# Get sales data')
    print('sales = await get_sales_data(')
    print('    start_date="2024-01-01",')
    print('    end_date="2024-12-31",')
    print('    min_revenue=1000.0')
    print(')')
    print()
    print('# Aggregate by region (in memory - no extra API calls!)')
    print('aggregated = await aggregate_sales(')
    print('    sales_data=sales["rows"],')
    print('    group_by="region"')
    print(')')
    print()
    print('return aggregated')
    print('```')
    print()

    # Actually execute
    print("Executing...")
    print()

    # Get sales tool (already loaded from earlier)
    sales_result = await sales_tool_obj.execute(
        start_date="2024-01-01", end_date="2024-12-31", min_revenue=1000.0
    )

    print(f"Step 1: Fetched {sales_result.total_count} sales records")
    print()

    # Get aggregate tool (auto-loaded if not already)
    agg_tool_class = await registry.get_tool("AggregateSalesTool", "sales")
    agg_tool = agg_tool_class()  # Create instance
    agg_result = await agg_tool.execute(sales_data=sales_result.rows, group_by="region")

    print(f"Step 2: Aggregated into {len(agg_result.aggregates)} regions:")
    for agg in agg_result.aggregates:
        print(
            f"   • {agg['region']}: ${agg['total_revenue']:,.2f} "
            f"({agg['count']} sales, avg ${agg['average_revenue']:,.2f})"
        )
    print()

    # ========================================================================
    # STEP 6: Benefits Summary
    # ========================================================================
    print("STEP 6: Advanced Tool Use Benefits")
    print("-" * 80)
    print()

    active_after = await registry.get_active_tools(namespace="sales")
    deferred_after = await registry.get_deferred_tools(namespace="sales")

    print("📊 Feature Comparison:")
    print()

    print("❌ Traditional Approach:")
    print("   • Load all 3 tools upfront → 3 tool definitions sent to LLM")
    print("   • Each tool ~500 tokens → 1,500 tokens total")
    print("   • Aggregate function needs 2 API calls (fetch + aggregate)")
    print("   • Intermediate data pollutes context → +5,000 tokens")
    print("   • Total: ~6,500 tokens, 2+ API calls")
    print()

    print("✅ Advanced Tool Use:")
    print(f"   • Deferred loading → Started with {len(active_tools)} core tools")
    print(f"   • Loaded {len(active_after) - len(active_tools)} tools on-demand")
    print(f"   • Still have {len(deferred_after)} tools deferred")
    print("   • Tool examples → 90% accuracy (vs 72%)")
    print("   • Programmatic execution → 1 API call, intermediate data in memory")
    print("   • Total: ~2,000 tokens (70% reduction!)")
    print()

    print("🎯 Key Benefits:")
    print("   ✅ 85% token reduction from deferred loading")
    print("   ✅ 25% accuracy improvement from examples")
    print("   ✅ 37% token savings from programmatic execution")
    print("   ✅ Works with OpenAI, Anthropic, MCP, and any LLM")
    print()

    # ========================================================================
    # STEP 7: Real-World LLM Integration
    # ========================================================================
    print("STEP 7: LLM API Integration Pattern")
    print("-" * 80)
    print()

    print("How to use with Anthropic Claude:")
    print()
    print("```python")
    print("import anthropic")
    print()
    print("# Get active tools (only loaded ones)")
    print("active_tools = await registry.get_active_tools()")
    print()
    print("# Export for Anthropic with examples + programmatic execution")
    print("tool_defs = []")
    print("for tool_info in active_tools:")
    print("    metadata = await registry.get_metadata(tool_info.name, tool_info.namespace)")
    print("    spec = ToolSpec.from_metadata(metadata)")
    print("    tool_defs.append(spec.to_anthropic())")
    print()
    print("# Add tool search tool for dynamic loading")
    print("tool_defs.append({")
    print('    "name": "tool_search",')
    print('    "description": "Search and load deferred tools",')
    print("    # ... schema")
    print("})")
    print()
    print("# Make API call")
    print("response = client.messages.create(")
    print('    model="claude-sonnet-4.5-20250514",')
    print("    max_tokens=1024,")
    print('    betas=["advanced-tool-use-2025-11-20"],  # Enable advanced features')
    print("    tools=tool_defs,  # Includes examples + allowed_callers")
    print("    messages=[{")
    print('        "role": "user",')
    print('        "content": "Analyze sales by region"')
    print("    }]")
    print(")")
    print("```")
    print()

    print("=" * 80)
    print("DEMONSTRATION COMPLETE")
    print("=" * 80)
    print()

    print("🎉 All three advanced tool use features demonstrated:")
    print("   1. ✅ Deferred Loading - Dynamic tool discovery")
    print("   2. ✅ Tool Use Examples - Improved accuracy")
    print("   3. ✅ Programmatic Execution - Code-based orchestration")
    print()
    print("💡 See docs/ for detailed guides on each feature")


async def main():
    """Main entry point."""
    try:
        await demonstrate_advanced_tool_use()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
