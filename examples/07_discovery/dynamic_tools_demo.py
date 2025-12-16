#!/usr/bin/env python
"""
Dynamic Tool Discovery Demo - Let LLMs Find and Execute Tools On-Demand

This example demonstrates the discovery module's intelligent search capabilities:
- Synonym expansion ("gaussian" finds "normal_cdf")
- Fuzzy matching for typos ("calcualtor" finds "calculator")
- Two-stage search with fallback
- Session boosting for recently used tools
- Dynamic tool provider pattern for LLM integration

The discovery module bridges the gap between how LLMs naturally describe tools
and how tools are actually named in code.

Run this:
    uv run python examples/07_discovery/dynamic_tools_demo.py

Takes ~3 minutes to understand.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from chuk_tool_processor.discovery import (
    BaseDynamicToolProvider,
    SearchResult,
    ToolSearchEngine,
    tokenize,
    expand_with_synonyms,
    extract_keywords,
)


# ==============================================================================
# Step 1: Define some mock tools with the SearchableTool protocol
# ==============================================================================

@dataclass
class MockTool:
    """A minimal tool representation for demonstration.

    The discovery module uses duck typing (SearchableTool protocol),
    so any object with name, namespace, description, and parameters works.
    """
    name: str
    namespace: str
    description: str
    parameters: dict[str, Any] | None = None

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Execute the tool (mock implementation)."""
        return {"tool": self.name, "args": kwargs, "result": f"Executed {self.name}"}


# Create a set of math and utility tools for demonstration
DEMO_TOOLS = [
    # Statistics tools
    MockTool(
        name="normal_cdf",
        namespace="stats",
        description="Calculate cumulative distribution function for normal distribution",
        parameters={"type": "object", "properties": {"x": {"type": "number"}, "mean": {"type": "number"}, "std": {"type": "number"}}},
    ),
    MockTool(
        name="normal_pdf",
        namespace="stats",
        description="Calculate probability density function for normal/Gaussian distribution",
        parameters={"type": "object", "properties": {"x": {"type": "number"}, "mean": {"type": "number"}, "std": {"type": "number"}}},
    ),
    MockTool(
        name="calculate_mean",
        namespace="stats",
        description="Calculate the arithmetic mean (average) of a list of numbers",
        parameters={"type": "object", "properties": {"values": {"type": "array", "items": {"type": "number"}}}},
    ),
    MockTool(
        name="calculate_std",
        namespace="stats",
        description="Calculate the standard deviation of a list of numbers",
        parameters={"type": "object", "properties": {"values": {"type": "array", "items": {"type": "number"}}}},
    ),

    # Arithmetic tools
    MockTool(
        name="add",
        namespace="math",
        description="Add two numbers together",
        parameters={"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}},
    ),
    MockTool(
        name="multiply",
        namespace="math",
        description="Multiply two numbers",
        parameters={"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}},
    ),
    MockTool(
        name="sqrt",
        namespace="math",
        description="Calculate the square root of a number",
        parameters={"type": "object", "properties": {"x": {"type": "number"}}},
    ),

    # File tools
    MockTool(
        name="read_file",
        namespace="files",
        description="Read contents from a file on disk",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
    ),
    MockTool(
        name="write_file",
        namespace="files",
        description="Write or save content to a file",
        parameters={"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}},
    ),
    MockTool(
        name="list_directory",
        namespace="files",
        description="List files and directories in a path",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
    ),
]


# ==============================================================================
# Step 2: Create a Dynamic Tool Provider
# ==============================================================================

class DemoToolProvider(BaseDynamicToolProvider[MockTool]):
    """A dynamic tool provider that allows LLMs to discover and execute tools.

    The LLM receives 4 meta-tools:
    - list_tools: See all available tools
    - search_tools: Find tools by natural language query
    - get_tool_schema: Get detailed parameter info for a tool
    - call_tool: Execute a discovered tool
    """

    def __init__(self, tools: list[MockTool]) -> None:
        super().__init__()
        self._tools = tools

    async def get_all_tools(self) -> list[MockTool]:
        """Return all available tools."""
        return self._tools

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool by name."""
        for tool in self._tools:
            if tool.name == tool_name:
                result = await tool.execute(**arguments)
                return {"success": True, "result": result}

        return {"success": False, "error": f"Tool '{tool_name}' not found"}

    def filter_search_results(
        self,
        results: list[SearchResult[MockTool]],
    ) -> list[SearchResult[MockTool]]:
        """Optional: Filter or modify search results.

        Override this to implement custom logic like:
        - Blocking tools that require authentication
        - Hiding tools based on user permissions
        - Modifying scores based on context
        """
        # For demo, we just pass through all results
        return results


# ==============================================================================
# Step 3: Demonstrate Search Capabilities
# ==============================================================================

async def demo_search_features() -> None:
    """Demonstrate the search engine's intelligent matching capabilities."""
    print("=" * 70)
    print("PART 1: Search Engine Features")
    print("=" * 70)
    print()

    engine: ToolSearchEngine[MockTool] = ToolSearchEngine()
    engine.set_tools(DEMO_TOOLS)

    # ---------------------------------------------------------------------
    # Demo 1: Synonym Expansion
    # ---------------------------------------------------------------------
    print("1. Synonym Expansion")
    print("   The search engine knows that 'gaussian' = 'normal', 'cdf' = 'cumulative'")
    print()

    query = "gaussian distribution cdf"
    results = engine.search(query, limit=3)

    print(f"   Query: '{query}'")
    print(f"   Results:")
    for r in results:
        print(f"     - {r.name} (score: {r.score:.1f})")
        print(f"       Reasons: {', '.join(r.match_reasons)}")
    print()

    # Show the synonym expansion
    keywords = extract_keywords(query)
    expanded = expand_with_synonyms(keywords)
    print(f"   Keywords: {keywords}")
    print(f"   Expanded with synonyms: {expanded}")
    print()

    # ---------------------------------------------------------------------
    # Demo 2: Natural Language Queries
    # ---------------------------------------------------------------------
    print("2. Natural Language Queries")
    print("   LLMs often describe what they want, not the exact function name")
    print()

    queries = [
        "find the average of numbers",      # Should find calculate_mean
        "save data to disk",                # Should find write_file
        "bell curve probability",           # Should find normal_pdf
    ]

    for query in queries:
        results = engine.search(query, limit=2)
        print(f"   Query: '{query}'")
        print(f"   Top match: {results[0].name if results else 'None'}")
        if results:
            print(f"   Score: {results[0].score:.1f}, Reasons: {results[0].match_reasons}")
        print()

    # ---------------------------------------------------------------------
    # Demo 3: Fuzzy Matching for Typos
    # ---------------------------------------------------------------------
    print("3. Fuzzy Matching (Typo Tolerance)")
    print("   Handles common typos and close matches")
    print()

    typo_queries = [
        "noraml_cdf",      # Typo in 'normal'
        "multipley",       # Typo in 'multiply'
        "calclate mean",   # Typo in 'calculate'
    ]

    for query in typo_queries:
        results = engine.search(query, limit=1)
        print(f"   Query: '{query}' (with typo)")
        if results:
            print(f"   Found: {results[0].name} (score: {results[0].score:.1f})")
        print()

    # ---------------------------------------------------------------------
    # Demo 4: Tokenization
    # ---------------------------------------------------------------------
    print("4. Tokenization (How Names Are Parsed)")
    print("   Handles snake_case, camelCase, kebab-case, dot.notation")
    print()

    examples = ["normal_cdf", "normalCdf", "calculate-mean", "stats.normal_cdf"]
    for name in examples:
        tokens = tokenize(name)
        print(f"   '{name}' -> {tokens}")
    print()


async def demo_session_boosting() -> None:
    """Demonstrate session-aware search boosting."""
    print("=" * 70)
    print("PART 2: Session Boosting")
    print("=" * 70)
    print()

    print("Recently used tools get boosted in search results.")
    print("This helps LLMs find tools they've used successfully before.")
    print()

    engine: ToolSearchEngine[MockTool] = ToolSearchEngine()
    engine.set_tools(DEMO_TOOLS)

    # Search before any tool use
    print("Before any tool use:")
    results = engine.search("calculate", limit=3)
    for r in results:
        print(f"  {r.name}: score={r.score:.1f}")
    print()

    # Simulate using calculate_mean successfully
    engine.record_tool_use("calculate_mean", success=True)
    engine.record_tool_use("calculate_mean", success=True)
    engine.advance_turn()

    print("After using 'calculate_mean' twice successfully:")
    results = engine.search("calculate", limit=3)
    for r in results:
        boost_info = ""
        if "session_boost" in str(r.match_reasons):
            boost_info = " (boosted!)"
        print(f"  {r.name}: score={r.score:.1f}{boost_info}")
        if r.match_reasons:
            print(f"    Reasons: {r.match_reasons}")
    print()


async def demo_dynamic_provider() -> None:
    """Demonstrate the dynamic tool provider pattern for LLM integration."""
    print("=" * 70)
    print("PART 3: Dynamic Tool Provider (LLM Integration)")
    print("=" * 70)
    print()

    print("The BaseDynamicToolProvider gives LLMs 5 meta-tools:")
    print("  1. list_tools      - See what's available")
    print("  2. search_tools    - Find tools by description")
    print("  3. get_tool_schema - Get parameter details for one tool")
    print("  4. get_tool_schemas - Get schemas for multiple tools (batch)")
    print("  5. call_tool       - Execute a discovered tool")
    print()

    provider = DemoToolProvider(DEMO_TOOLS)

    # Show the dynamic tool definitions (what the LLM sees)
    print("Dynamic tool definitions (sent to LLM):")
    dynamic_tools = provider.get_dynamic_tools()
    for tool in dynamic_tools:
        func = tool["function"]
        print(f"  - {func['name']}: {func['description'][:60]}...")
    print()

    # Simulate LLM workflow
    print("-" * 50)
    print("Simulating LLM Workflow:")
    print("-" * 50)
    print()

    # Step 1: LLM lists tools
    print("Step 1: LLM calls list_tools(limit=5)")
    result = await provider.execute_dynamic_tool("list_tools", {"limit": 5})
    print(f"  Found {result['count']} of {result['total_available']} tools:")
    for tool in result["result"]:  # Note: unified format uses 'result' not 'results'
        print(f"    - {tool['namespace']}.{tool['name']}: {tool['description'][:40]}...")
    print()

    # Step 2: LLM searches for what it needs
    print("Step 2: LLM calls search_tools(query='calculate average')")
    result = await provider.execute_dynamic_tool("search_tools", {"query": "calculate average", "limit": 3})
    print(f"  Found {result['count']} matching tools:")
    for tool in result["result"]:  # Note: unified format uses 'result' not 'results'
        print(f"    - {tool['name']} (score: {tool['score']:.1f})")
        print(f"      Reasons: {tool['match_reasons']}")
    print()

    # Step 3: LLM gets the schema for the tool it wants
    print("Step 3: LLM calls get_tool_schema(tool_name='calculate_mean')")
    schema = await provider.execute_dynamic_tool("get_tool_schema", {"tool_name": "calculate_mean"})
    if "function" in schema:
        func = schema["function"]
        print(f"  Name: {func['name']}")
        print(f"  Description: {func['description']}")
        print(f"  Parameters: {func['parameters']}")
    print()

    # Step 4: LLM executes the tool
    print("Step 4: LLM calls call_tool(tool_name='calculate_mean', values=[1, 2, 3, 4, 5])")
    result = await provider.execute_dynamic_tool("call_tool", {
        "tool_name": "calculate_mean",
        "values": [1, 2, 3, 4, 5],
    })
    print(f"  Result: {result}")
    print()


async def demo_alias_resolution() -> None:
    """Demonstrate tool name alias resolution."""
    print("=" * 70)
    print("PART 4: Name Alias Resolution")
    print("=" * 70)
    print()

    print("Tools can be found by various name forms:")
    print("  - Exact name: 'normal_cdf'")
    print("  - With namespace: 'stats.normal_cdf'")
    print("  - camelCase: 'normalCdf'")
    print("  - No separators: 'normalcdf'")
    print()

    provider = DemoToolProvider(DEMO_TOOLS)

    aliases = ["normal_cdf", "stats.normal_cdf", "normalCdf", "normalcdf"]

    for alias in aliases:
        schema = await provider.get_tool_schema(alias)
        if "function" in schema:
            print(f"  '{alias}' -> Found: {schema['function']['name']}")
        else:
            print(f"  '{alias}' -> {schema.get('error', 'Not found')}")
    print()


async def main() -> None:
    """Run all demonstrations."""
    print()
    print("=" * 70)
    print("Dynamic Tool Discovery Demo")
    print("=" * 70)
    print()
    print("This demo shows how the discovery module helps LLMs find tools")
    print("using natural language, synonyms, and fuzzy matching.")
    print()

    await demo_search_features()
    await demo_session_boosting()
    await demo_dynamic_provider()
    await demo_alias_resolution()

    print("=" * 70)
    print("Summary: Key Features")
    print("=" * 70)
    print()
    print("1. Synonym Expansion")
    print("   'gaussian' finds 'normal', 'cdf' finds 'cumulative'")
    print()
    print("2. Natural Language Queries")
    print("   'find the average' finds 'calculate_mean'")
    print()
    print("3. Fuzzy Matching")
    print("   'multipley' finds 'multiply' (typo tolerance)")
    print()
    print("4. Session Boosting")
    print("   Recently used tools rank higher in results")
    print()
    print("5. Alias Resolution")
    print("   'normalCdf' and 'normal_cdf' both work")
    print()
    print("6. Dynamic Provider Pattern")
    print("   Give LLMs 5 meta-tools to discover and execute tools on-demand")
    print()
    print("7. Batch Schema Fetching")
    print("   get_tool_schemas() fetches multiple schemas in one call")
    print()
    print("8. Unified Response Format")
    print("   All responses use {success: bool, result/error: ...}")
    print()
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
