#!/usr/bin/env python
# examples/mcp_http_streamable_example.py
"""
Demo: wire a remote MCP server via **HTTP Streamable** transport to CHUK.

Prerequisites
-------------
- A running HTTP Streamable MCP server at localhost:8000
- The server should expose HTTP tools (http_greet, session_info, etc.)

What it shows
-------------
1. Connect to an HTTP Streamable MCP server at localhost:8000 with proper MCP initialization
2. Register the remote tools in the local CHUK registry
3. List everything that landed in the registry
4. Look up the wrapper for HTTP tools and call them directly
5. Test multiple queries with different HTTP Streamable tools
6. Demonstrate the modern single-endpoint approach (spec 2025-03-26)
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
from chuk_tool_processor.mcp.setup_mcp_http_streamable import setup_mcp_http_streamable
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
    print("=== MCP HTTP Streamable Integration Demo ===\n")
    print("Using modern MCP Streamable HTTP transport (spec 2025-03-26)")
    print("This replaces the deprecated SSE transport with better infrastructure compatibility.\n")

    # 1️⃣  setup HTTP Streamable transport + registry
    try:
        print("🔄 Connecting to MCP HTTP Streamable server...")
        processor, stream_manager = await setup_mcp_http_streamable(
            servers=[
                {
                    "name": "http_demo_server",
                    "url": "http://localhost:8000",  # Single endpoint approach
                    # Optional: add API key if your server requires it
                    # "api_key": "your-api-key-here"
                    # Optional: add session ID for stateful connections
                    # "session_id": "demo-session-123"
                }
            ],
            server_names={0: "http_demo_server"},
            namespace="http",
        )
        print("✅ Successfully connected to MCP HTTP Streamable server!")
    except Exception as e:
        print(f"❌ Failed to connect to HTTP Streamable server: {e}")
        print("Make sure you have an HTTP Streamable MCP server running at http://localhost:8000")
        print("The server should expose HTTP tools like 'http_greet', 'session_info'")
        return

    # 2️⃣  show what tools we got
    await dump_namespace("http")

    # 3️⃣  test http_greet tool
    print("\n" + "="*60)
    print("Testing http_greet tool...")
    registry = await ToolRegistryProvider.get_registry()
    wrapper_cls = await registry.get_tool("http_greet", "http")

    if wrapper_cls is None:
        print("❌ http_greet tool not found in registry")
        print("Available tools:")
        tools = await registry.list_tools("http")
        for ns, name in tools:
            print(f"  - {name}")
        await stream_manager.close()
        return

    # 4️⃣  execute http_greet with sample parameters
    wrapper = wrapper_cls() if callable(wrapper_cls) else wrapper_cls
    try:
        name = "HTTP Streamable User"
        style = "formal"
        print(f"🌐 Greeting: {name} ({style} style)")
        
        res = await wrapper.execute(name=name, style=style)
        print("\n📋 Result:")
        print(res)
    except Exception as exc:
        print(f"❌ http_greet execution failed: {exc}")

    # 5️⃣  test multiple HTTP Streamable tools
    print("\n" + "="*60)
    print("Testing all available HTTP Streamable tools...")
    
    test_scenarios = [
        {
            "tool": "http_greet",
            "args": {"name": "Alice", "style": "casual"},
            "description": "Casual greeting via HTTP transport"
        },
        {
            "tool": "session_info", 
            "args": {},
            "description": "Get current HTTP session information"
        },
        {
            "tool": "http_counter",
            "args": {"increment": 3},
            "description": "Increment session counter"
        },
        {
            "tool": "slow_operation",
            "args": {"duration": 2},
            "description": "Test slow operation (may use streaming)"
        }
    ]
    
    for i, scenario in enumerate(test_scenarios, 1):
        tool_name = scenario["tool"]
        args = scenario["args"]
        description = scenario["description"]
        
        print(f"\n📝 Test {i}: {tool_name} - {description}")
        print(f"   Args: {args}")
        
        # Get tool wrapper
        tool_wrapper_cls = await registry.get_tool(tool_name, "http")
        
        if tool_wrapper_cls is None:
            print(f"   ⚠️  Tool '{tool_name}' not available")
            continue
            
        try:
            tool_wrapper = tool_wrapper_cls() if callable(tool_wrapper_cls) else tool_wrapper_cls
            res = await tool_wrapper.execute(**args)
            
            print("   ✅ Success!")
            if isinstance(res, str):
                # Truncate long responses for readability
                if len(res) > 200:
                    res = res[:200] + "..."
                print(f"   📋 Response: {res}")
            elif isinstance(res, (dict, list)):
                print(f"   📋 Result: {json.dumps(res, indent=6)}")
            else:
                print(f"   📋 Result: {res}")
                
        except Exception as exc:
            print(f"   ❌ Failed: {exc}")

    # 6️⃣  demonstrate HTTP Streamable advantages
    print("\n" + "="*60)
    print("HTTP Streamable Transport Advantages:")
    print("🌐 Single endpoint approach (/mcp)")
    print("🔄 Better infrastructure compatibility")
    print("⚡ Supports both immediate JSON and streaming SSE responses")
    print("🛡️  Enhanced error handling and retry logic")
    print("🔧 Stateless operation when streaming not needed")
    print("📊 Modern replacement for deprecated SSE transport")

    # 7️⃣  show session persistence if supported
    print("\n" + "="*60)
    print("Testing session persistence...")
    
    # Call counter multiple times to show session state
    counter_wrapper_cls = await registry.get_tool("http_counter", "http")
    if counter_wrapper_cls:
        counter_wrapper = counter_wrapper_cls() if callable(counter_wrapper_cls) else counter_wrapper_cls
        
        try:
            print("📊 First counter call...")
            res1 = await counter_wrapper.execute(increment=1)
            print(f"   Result: {res1}")
            
            print("📊 Second counter call...")
            res2 = await counter_wrapper.execute(increment=2)
            print(f"   Result: {res2}")
            
            # Get session info to see the accumulated state
            session_wrapper_cls = await registry.get_tool("session_info", "http")
            if session_wrapper_cls:
                session_wrapper = session_wrapper_cls() if callable(session_wrapper_cls) else session_wrapper_cls
                session_info = await session_wrapper.execute()
                print(f"📋 Final session state: {session_info}")
                
        except Exception as exc:
            print(f"❌ Session persistence test failed: {exc}")

    # 8️⃣  show server capabilities
    print("\n" + "="*60)
    print("MCP HTTP Streamable Server Information:")
    print("✅ HTTP Streamable transport (spec 2025-03-26)")
    print("✅ Single /mcp endpoint for all communication")
    print("✅ JSON-RPC 2.0 protocol compliance")
    print("✅ Tool discovery and execution")
    print("✅ Session management support")
    print("✅ Optional streaming for complex operations")
    print("✅ Better infrastructure compatibility than SSE")

    # 9️⃣  tidy-up
    print("\n🔄 Closing connections...")
    await stream_manager.close()
    print("✅ HTTP Streamable demo completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())