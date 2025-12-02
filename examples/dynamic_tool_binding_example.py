#!/usr/bin/env python3
"""
Dynamic Tool Binding Example

This example demonstrates how to use deferred tool loading to break through
the 128 function limit of most LLM APIs.

Key concepts:
1. Only load "core" tools initially (< 128 tools)
2. Use tool_search to dynamically discover and load tools on-demand
3. Scale to thousands of tools without hitting API limits

Run this example:
    python examples/dynamic_tool_binding_example.py
"""

import asyncio

from chuk_tool_processor.registry import get_default_registry


async def main():
    """Demonstrate dynamic tool binding."""
    print("=" * 70)
    print("DYNAMIC TOOL BINDING EXAMPLE")
    print("=" * 70)
    print()

    # Initialize the registry
    registry = await get_default_registry()

    # Step 1: Check initially loaded tools
    print("STEP 1: Initial Tool State")
    print("-" * 70)

    active_tools = await registry.get_active_tools()
    print(f"✓ Active tools (loaded): {len(active_tools)}")
    for tool in active_tools:
        print(f"  - {tool.namespace}:{tool.name}")

    deferred_tools = await registry.get_deferred_tools()
    print(f"\n✓ Deferred tools (not yet loaded): {len(deferred_tools)}")
    for tool in deferred_tools[:5]:  # Show first 5
        print(f"  - {tool.namespace}:{tool.name}")
    if len(deferred_tools) > 5:
        print(f"  ... and {len(deferred_tools) - 5} more")

    print()

    # Step 2: Search for tools
    print("STEP 2: Dynamic Tool Discovery")
    print("-" * 70)

    # Search for CSV-related tools
    print("Searching for 'csv' tools...")
    csv_tools = await registry.search_deferred_tools(query="csv", limit=3)

    if csv_tools:
        print(f"✓ Found {len(csv_tools)} matching tools:")
        for tool_meta in csv_tools:
            print(f"  - {tool_meta.namespace}:{tool_meta.name}")
            print(f"    Description: {tool_meta.description}")
            print(f"    Keywords: {', '.join(tool_meta.search_keywords)}")
        print()
    else:
        print("  (No CSV tools found - they may not be imported)")
        print()

    # Step 3: Load a deferred tool on-demand
    print("STEP 3: Loading Tools On-Demand")
    print("-" * 70)

    # Try to load a tool from sample_tools
    try:
        # Import sample_tools to register them
        import sample_tools.deferred_example_tool  # noqa: F401

        # Re-check deferred tools after import
        deferred_tools = await registry.get_deferred_tools()
        if deferred_tools:
            tool_to_load = deferred_tools[0]
            print(f"Loading tool: {tool_to_load.namespace}:{tool_to_load.name}")

            loaded_tool = await registry.load_deferred_tool(
                tool_to_load.name,
                tool_to_load.namespace
            )
            print(f"✓ Successfully loaded: {loaded_tool}")

            # Verify it's now active
            active_after = await registry.get_active_tools()
            print(f"✓ Active tools now: {len(active_after)} (was {len(active_tools)})")
        else:
            print("  (No deferred tools available to load)")
    except ImportError as e:
        print(f"  Note: sample_tools not available ({e})")

    print()

    # Step 4: Demonstrate the value proposition
    print("STEP 4: The Value Proposition")
    print("-" * 70)
    print()
    print("🎯 Breaking the 128 Function Limit:")
    print()
    print("Traditional approach:")
    print("  ❌ Load all 500 tools → Hit API limit")
    print("  ❌ Can't use most tools")
    print()
    print("Dynamic tool binding approach:")
    print("  ✅ Load 10 core tools initially")
    print("  ✅ Use tool_search to find needed tools")
    print("  ✅ Load tools on-demand (only what's needed)")
    print("  ✅ Scale to unlimited tools!")
    print()

    # Step 5: Show API binding workflow
    print("STEP 5: LLM API Integration Workflow")
    print("-" * 70)
    print()
    print("1. Initial API call with core tools only:")
    print("   tools = [tool_search, calculator, web_search] # Only 3 tools")
    print()
    print("2. Claude decides it needs CSV tools:")
    print("   → Calls tool_search(query='csv data parsing')")
    print()
    print("3. Tool search loads CSV tools dynamically:")
    print("   → Loads: csv_parser, pandas_read_csv, data_validator")
    print()
    print("4. Next API call includes newly loaded tools:")
    print("   tools = [tool_search, calculator, web_search,")
    print("           csv_parser, pandas_read_csv, data_validator]")
    print()
    print("5. Claude can now use CSV tools:")
    print("   → Calls csv_parser(data='...')")
    print()

    # Step 6: Real-world example
    print("STEP 6: Real-World Scenario")
    print("-" * 70)
    print()
    print("Scenario: Database tool library with 500 tools")
    print()
    print("Tool organization:")
    print("  • postgres namespace: 200 tools")
    print("  • mongodb namespace: 150 tools")
    print("  • redis namespace: 100 tools")
    print("  • mysql namespace: 50 tools")
    print()
    print("Without defer_loading:")
    print("  ❌ 500 tools > 128 limit → ERROR")
    print()
    print("With defer_loading:")
    print("  ✅ Core tools loaded: 5 (tool_search + common utils)")
    print("  ✅ User: 'Query my PostgreSQL database'")
    print("  ✅ Claude: tool_search(query='postgres query')")
    print("  ✅ System: Loads 3 postgres tools")
    print("  ✅ Claude: Uses postgres_query tool")
    print("  ✅ Success! Only 8 tools loaded total")
    print()

    print("=" * 70)
    print("Example complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
