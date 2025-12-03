#!/usr/bin/env python3
"""
MCP Deferred Loading Example

This example shows how to use deferred loading with MCP servers to handle
servers that expose hundreds of tools.

Key concepts:
1. MCP servers can expose 100+ tools
2. Use defer_loading to only load core tools initially
3. Search and load specialized tools on-demand
4. Scale to unlimited MCP tools

Usage:
    # Mock mode (no real MCP server needed)
    python examples/mcp_deferred_loading_example.py

    # With real MCP server
    python examples/mcp_deferred_loading_example.py --server stdio path/to/server
"""

import asyncio
from typing import Any

from chuk_tool_processor.mcp.register_mcp_tools import register_mcp_tools
from chuk_tool_processor.registry import get_default_registry, reset_registry


class MockStreamManager:
    """Mock StreamManager for demonstration."""

    def __init__(self, tools: list[dict[str, Any]]):
        self._tools = tools

    def get_all_tools(self) -> list[dict[str, Any]]:
        """Return all tools."""
        return self._tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Mock tool call."""
        return {"result": f"Mock result from {tool_name}", "arguments": arguments}


def create_mock_mcp_server_with_many_tools() -> MockStreamManager:
    """Create a mock MCP server with 50 tools."""
    tools = []

    # Core tools (should not be deferred)
    tools.extend([
        {
            "name": "get_config",
            "description": "Get server configuration",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "health_check",
            "description": "Check server health",
            "inputSchema": {"type": "object", "properties": {}}
        },
    ])

    # Database tools (should be deferred)
    for i in range(10):
        tools.append({
            "name": f"db_query_{i}",
            "description": f"Execute database query operation {i}",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL query"}
                }
            }
        })

    # File tools (should be deferred)
    for i in range(10):
        tools.append({
            "name": f"file_operation_{i}",
            "description": f"Perform file operation {i} like read, write, delete",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"}
                }
            }
        })

    # API tools (should be deferred)
    for i in range(10):
        tools.append({
            "name": f"api_call_{i}",
            "description": f"Make HTTP API call to external service {i}",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "API endpoint"}
                }
            }
        })

    # ML tools (should be deferred)
    for i in range(10):
        tools.append({
            "name": f"ml_model_{i}",
            "description": f"Run machine learning model {i} for inference and prediction",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "features": {"type": "array", "description": "Input features"}
                }
            }
        })

    # Data processing tools (should be deferred)
    for i in range(8):
        tools.append({
            "name": f"data_transform_{i}",
            "description": f"Transform and process data using operation {i}",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "data": {"type": "object", "description": "Input data"}
                }
            }
        })

    return MockStreamManager(tools)


async def demonstrate():
    """Demonstrate MCP deferred loading."""
    print("=" * 80)
    print("MCP DEFERRED LOADING DEMONSTRATION")
    print("=" * 80)
    print()

    # Reset registry
    await reset_registry()

    # Create mock MCP server with 50 tools
    print("Setting up mock MCP server with 50 tools...")
    stream_manager = create_mock_mcp_server_with_many_tools()
    all_tools = stream_manager.get_all_tools()
    print(f"✅ Mock server created with {len(all_tools)} tools")
    print()

    # ========================================================================
    # STEP 1: Register with deferred loading
    # ========================================================================
    print("STEP 1: Register MCP Tools with Deferred Loading")
    print("-" * 80)

    # Register tools: defer all except core tools
    print("\nRegistering tools...")
    print("  • Core tools (eager): get_config, health_check")
    print("  • All others (deferred): db_query_*, file_operation_*, etc.")
    print()

    registered = await register_mcp_tools(
        stream_manager=stream_manager,
        namespace="mcp_demo",
        defer_loading=True,  # Defer all by default
        defer_all_except=["get_config", "health_check"],  # Don't defer these
    )

    print(f"✅ Registered {len(registered)} tools")
    print()

    # ========================================================================
    # STEP 2: Check initial state
    # ========================================================================
    print("STEP 2: Initial Tool State")
    print("-" * 80)

    registry = await get_default_registry()

    active_tools = await registry.get_active_tools(namespace="mcp_demo")
    deferred_tools = await registry.get_deferred_tools(namespace="mcp_demo")

    print(f"\n✅ Active tools (loaded): {len(active_tools)}")
    for tool in active_tools:
        print(f"   • {tool.name}")

    print(f"\n✅ Deferred tools (NOT loaded): {len(deferred_tools)}")
    print(f"   • db_query_*: 10 tools")
    print(f"   • file_operation_*: 10 tools")
    print(f"   • api_call_*: 10 tools")
    print(f"   • ml_model_*: 10 tools")
    print(f"   • data_transform_*: 8 tools")

    print()

    # ========================================================================
    # STEP 3: Search for tools
    # ========================================================================
    print("STEP 3: Searching for Tools")
    print("-" * 80)

    print("\nSearching for 'database' tools...")
    db_results = await registry.search_deferred_tools(
        query="database query",
        limit=5
    )

    print(f"✅ Found {len(db_results)} matching tools:")
    for tool_meta in db_results:
        print(f"   • {tool_meta.name}: {tool_meta.description}")

    print("\nSearching for 'machine learning' tools...")
    ml_results = await registry.search_deferred_tools(
        query="machine learning model",
        limit=3
    )

    print(f"✅ Found {len(ml_results)} matching tools:")
    for tool_meta in ml_results:
        print(f"   • {tool_meta.name}: {tool_meta.description}")

    print()

    # ========================================================================
    # STEP 4: Load tools on-demand
    # ========================================================================
    print("STEP 4: Loading Tools On-Demand")
    print("-" * 80)

    print("\nLoading database tools...")
    for tool_meta in db_results[:2]:  # Load first 2
        print(f"   Loading {tool_meta.name}...")
        await registry.load_deferred_tool(tool_meta.name, tool_meta.namespace)

    print("\nLoading ML tools...")
    for tool_meta in ml_results[:1]:  # Load first 1
        print(f"   Loading {tool_meta.name}...")
        await registry.load_deferred_tool(tool_meta.name, tool_meta.namespace)

    # Check final state
    active_final = await registry.get_active_tools(namespace="mcp_demo")
    deferred_final = await registry.get_deferred_tools(namespace="mcp_demo")

    print(f"\n✅ Active tools now: {len(active_final)} (was {len(active_tools)})")
    print(f"✅ Deferred tools now: {len(deferred_final)} (was {len(deferred_tools)})")

    print()

    # ========================================================================
    # STEP 5: API Binding Simulation
    # ========================================================================
    print("STEP 5: LLM API Binding Simulation")
    print("-" * 80)

    print("\nScenario: MCP server with 50 tools")
    print()

    print("Traditional approach (NO deferred loading):")
    print("  ❌ Send all 50 tools to API")
    print("  ❌ If server has 200+ tools → Hit 128 limit!")
    print("  ❌ Large token usage for unused tools")
    print()

    print("Deferred loading approach:")
    print(f"  ✅ API Call #1: Send {len(active_tools)} tools (core only)")
    print("  ✅ User: 'Query the database...'")
    print("  ✅ Claude: tool_search(query='database')")
    print("  ✅ System: Loads 2 database tools")
    print(f"  ✅ API Call #2: Send {len(active_final)} tools")
    print("  ✅ Claude: Uses db_query_0 tool")
    print("  ✅ Success with minimal tool loading!")
    print()

    # ========================================================================
    # STEP 6: Real-world scenarios
    # ========================================================================
    print("STEP 6: Real-World MCP Scenarios")
    print("-" * 80)
    print()

    scenarios = [
        {
            "name": "Filesystem MCP Server",
            "tools": 150,
            "defer": "All except: ls, cd, pwd",
            "load_on_demand": "read_file, write_file when needed"
        },
        {
            "name": "Database MCP Server",
            "tools": 200,
            "defer": "All except: connect, disconnect",
            "load_on_demand": "query, insert, update when needed"
        },
        {
            "name": "Cloud Provider MCP",
            "tools": 500,
            "defer": "All except: auth, list_services",
            "load_on_demand": "EC2, S3, Lambda tools per user request"
        },
    ]

    for scenario in scenarios:
        print(f"📦 {scenario['name']}")
        print(f"   Total tools: {scenario['tools']}")
        print(f"   Eager load: {scenario['defer']}")
        print(f"   Deferred: {scenario['load_on_demand']}")
        print()

    print("=" * 80)
    print("DEMONSTRATION COMPLETE")
    print("=" * 80)
    print()
    print("Key Takeaways:")
    print("  1. MCP servers can expose 100+ tools")
    print("  2. defer_loading=True defers all except specified tools")
    print("  3. search_deferred_tools() finds tools by description")
    print("  4. Tools are loaded on-demand when needed")
    print("  5. This breaks the 128 function limit for MCP servers!")
    print()


if __name__ == "__main__":
    asyncio.run(demonstrate())
