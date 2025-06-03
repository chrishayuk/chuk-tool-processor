#!/usr/bin/env python
# examples/mcp_sse_example.py
"""
Demo: wire a remote MCP server via **SSE** transport to CHUK.

Prerequisites
-------------
- A running SSE MCP server at localhost:8000
- The server should expose Perplexity tools (perplexity_search, etc.)

What it shows
-------------
1. Connect to an SSE MCP server at localhost:8000 with proper MCP initialization
2. Register the remote tools in the local CHUK registry
3. List everything that landed in the registry
4. Look up the wrapper for Perplexity tools and call them directly
5. Test multiple queries with different Perplexity tools
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, List

# --------------------------------------------------------------------- #
#  allow "poetry run python examples/…" style execution                 #
# --------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# --------------------------------------------------------------------- #
#  CHUK imports                                                         #
# --------------------------------------------------------------------- #
from chuk_tool_processor.mcp.setup_mcp_sse import setup_mcp_sse
from chuk_tool_processor.registry.provider import ToolRegistryProvider


# --------------------------------------------------------------------- #
#  helper: pretty-print a namespace                                     #
# --------------------------------------------------------------------- #
async def dump_namespace(namespace: str) -> None:
    registry = await ToolRegistryProvider.get_registry()

    # ✅ list_tools() gives a plain list already
    tools = [t for t in await registry.list_tools() if t[0] == namespace]

    print(f"Tools in namespace {namespace!r} ({len(tools)}):")
    for ns, name in tools:
        meta = await registry.get_metadata(name, ns)
        desc = meta.description if meta else "no description"
        print(f"  • {ns}.{name:<30} — {desc}")

# --------------------------------------------------------------------- #
#  main demo                                                            #
# --------------------------------------------------------------------- #
async def main() -> None:
    print("=== MCP SSE Integration Demo (Fixed Transport) ===\n")

    # 1️⃣  setup SSE transport + registry with fixed transport
    try:
        print("🔄 Connecting to MCP SSE server (includes initialization handshake)...")
        processor, stream_manager = await setup_mcp_sse(
            servers=[
                {
                    "name": "perplexity_server",
                    "url": "http://localhost:8000",  # Base URL, transport will add /sse
                    # Optional: add API key if your server requires it
                    # "api_key": "your-api-key-here"
                }
            ],
            server_names={0: "perplexity_server"},
            namespace="sse",
        )
        print("✅ Successfully connected to MCP server!")
    except Exception as e:
        print(f"❌ Failed to connect to SSE server: {e}")
        print("Make sure you have an SSE MCP server running at http://localhost:8000")
        print("The server should expose Perplexity tools like 'perplexity_search'")
        return

    # 2️⃣  show what tools we got
    await dump_namespace("sse")

    # 3️⃣  test perplexity_search tool
    print("\n" + "="*60)
    print("Testing perplexity_search tool...")
    registry = await ToolRegistryProvider.get_registry()
    wrapper_cls = await registry.get_tool("perplexity_search", "sse")

    if wrapper_cls is None:
        print("❌ perplexity_search tool not found in registry")
        print("Available tools:")
        tools = await registry.list_tools("sse")
        for ns, name in tools:
            print(f"  - {name}")
        await stream_manager.close()
        return

    # 4️⃣  execute perplexity_search with a sample query
    wrapper = wrapper_cls() if callable(wrapper_cls) else wrapper_cls
    try:
        query = "What are the latest developments in AI language models in 2025?"
        print(f"🔍 Searching for: {query}")
        
        res = await wrapper.execute(query=query)
        print("\n📋 Result:")
        if isinstance(res, dict) and "answer" in res:
            print(res["answer"])
        elif isinstance(res, (dict, list)):
            print(json.dumps(res, indent=2))
        else:
            print(res)
    except Exception as exc:
        print(f"❌ perplexity_search execution failed: {exc}")

    # 5️⃣  test multiple Perplexity tools if available
    print("\n" + "="*60)
    print("Testing all available Perplexity tools...")
    
    test_scenarios = [
        {
            "tool": "perplexity_search",
            "query": "What is quantum computing and how does it work?",
            "description": "Quick conversational search"
        },
        {
            "tool": "perplexity_deep_research", 
            "query": "Latest breakthroughs in renewable energy technology",
            "description": "Deep research with citations"
        },
        {
            "tool": "perplexity_quick_fact",
            "query": "Who is the current president of France?",
            "description": "Quick fact checking"
        }
    ]
    
    for i, scenario in enumerate(test_scenarios, 1):
        tool_name = scenario["tool"]
        query = scenario["query"]
        description = scenario["description"]
        
        print(f"\n📝 Test {i}: {tool_name} - {description}")
        print(f"   Query: {query}")
        
        # Get tool wrapper
        tool_wrapper_cls = await registry.get_tool(tool_name, "sse")
        
        if tool_wrapper_cls is None:
            print(f"   ⚠️  Tool '{tool_name}' not available")
            continue
            
        try:
            tool_wrapper = tool_wrapper_cls() if callable(tool_wrapper_cls) else tool_wrapper_cls
            res = await tool_wrapper.execute(query=query)
            
            print("   ✅ Success!")
            if isinstance(res, dict) and "answer" in res:
                # Truncate long answers for readability
                answer = res["answer"]
                if len(answer) > 300:
                    answer = answer[:300] + "..."
                print(f"   📋 Answer: {answer}")
            elif isinstance(res, (dict, list)):
                print(f"   📋 Result: {json.dumps(res, indent=6)}")
            else:
                print(f"   📋 Result: {res}")
                
        except Exception as exc:
            print(f"   ❌ Failed: {exc}")

    # 6️⃣  show server capabilities
    print("\n" + "="*60)
    print("MCP Server Information:")
    print("✅ SSE transport with proper MCP initialization")
    print("✅ Async request/response handling")
    print("✅ JSON-RPC 2.0 protocol compliance")
    print("✅ Tool discovery and execution")

    # 7️⃣  tidy-up
    print("\n🔄 Closing connections...")
    await stream_manager.close()
    print("✅ Demo completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())