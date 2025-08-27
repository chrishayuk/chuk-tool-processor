#!/usr/bin/env python
"""
registry_diagnostic.py
─────────────────────
Diagnostic tool to understand exactly what's happening with tool registration
and lookup in the MCP system. This will help us identify the root cause of the
"Tool not found" errors even though tools appear to be registered.
"""

import asyncio
import json
import sys
from pathlib import Path

# ─── local-package bootstrap ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.mcp.setup_mcp_stdio import setup_mcp_stdio
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.registry.provider import ToolRegistryProvider

logger = get_logger("registry-diagnostic")


async def create_test_config():
    """Create test configuration."""
    config_file = PROJECT_ROOT / "diagnostic_config.json"
    config = {
        "mcpServers": {
            "time_test": {"command": "uvx", "args": ["mcp-server-time", "--local-timezone=America/New_York"]}
        }
    }

    config_file.write_text(json.dumps(config, indent=2))
    return str(config_file)


async def diagnostic_registry_deep_dive():
    """Perform deep diagnostic of the registry system."""
    print("🔍 Starting Registry Diagnostic...")

    # Create test config
    config_file = await create_test_config()

    try:
        print("\n1️⃣ Setting up MCP connection...")
        processor, stream_manager = await setup_mcp_stdio(
            config_file=config_file, servers=["time_test"], namespace="diagnostic_test", default_timeout=5.0
        )

        print("✅ MCP connection established")

        print("\n2️⃣ Examining Registry State...")
        registry = await ToolRegistryProvider.get_registry()

        # Get all tools in registry
        all_tools = await registry.list_tools()
        print(f"📊 Total tools in registry: {len(all_tools)}")

        for namespace, tool_name in all_tools:
            print(f"   • {namespace}.{tool_name}")

        # Get all namespaces
        namespaces = await registry.list_namespaces()
        print(f"📋 Namespaces: {namespaces}")

        # Focus on our test namespace
        test_namespace = "diagnostic_test"
        test_tools = [tool_name for ns, tool_name in all_tools if ns == test_namespace]
        print(f"\n🎯 Tools in '{test_namespace}' namespace: {test_tools}")

        if test_tools:
            test_tool = test_tools[0]
            print(f"\n3️⃣ Examining tool '{test_tool}' in detail...")

            # Get the tool object
            tool_obj = await registry.get_tool(test_tool, test_namespace)
            print(f"   Tool object: {type(tool_obj)} - {tool_obj}")
            print(f"   Tool has execute method: {hasattr(tool_obj, 'execute')}")

            if hasattr(tool_obj, "execute"):
                print(f"   Execute method is async: {asyncio.iscoroutinefunction(tool_obj.execute)}")

            # Get tool metadata
            metadata = await registry.get_metadata(test_tool, test_namespace)
            if metadata:
                print(f"   Metadata: {metadata.name} in {metadata.namespace}")
                print(f"   Description: {metadata.description}")
                print(f"   Tags: {metadata.tags}")

            print("\n4️⃣ Testing direct tool execution...")

            # Try direct execution
            try:
                if hasattr(tool_obj, "execute"):
                    print("   Attempting direct tool.execute()...")
                    result = await tool_obj.execute(timezone="UTC")
                    print(f"   ✅ Direct execution successful: {result}")
                else:
                    print("   ❌ Tool has no execute method")
            except Exception as e:
                print(f"   ❌ Direct execution failed: {e}")

            print("\n5️⃣ Testing via ToolExecutor...")

            # Test via executor
            executor = ToolExecutor(registry, strategy=InProcessStrategy(registry, default_timeout=5.0))

            # Try different tool name formats
            test_formats = [
                test_tool,  # Just the tool name
                f"{test_namespace}.{test_tool}",  # Namespace.tool format
            ]

            for tool_format in test_formats:
                print(f"   Testing format: '{tool_format}'")

                try:
                    call = ToolCall(tool=tool_format, arguments={"timezone": "UTC"})

                    results = await executor.execute([call])
                    result = results[0]

                    if result.error:
                        print(f"     ❌ Error: {result.error}")
                    else:
                        print(f"     ✅ Success: {result.result}")

                except Exception as e:
                    print(f"     ❌ Exception: {e}")

            print("\n6️⃣ Testing InProcessStrategy directly...")

            # Test strategy directly
            strategy = InProcessStrategy(registry, default_timeout=5.0)

            try:
                call = ToolCall(tool=test_tool, arguments={"timezone": "UTC"})
                results = await strategy.run([call])
                result = results[0]

                if result.error:
                    print(f"   ❌ Strategy error: {result.error}")
                else:
                    print(f"   ✅ Strategy success: {result.result}")

            except Exception as e:
                print(f"   ❌ Strategy exception: {e}")

            print("\n7️⃣ Registry Lookup Tests...")

            # Test different lookup methods
            lookup_tests = [
                (test_tool, test_namespace),
                (test_tool, "default"),
                (f"{test_namespace}.{test_tool}", test_namespace),
                (f"{test_namespace}.{test_tool}", "default"),
            ]

            for tool_name, namespace in lookup_tests:
                print(f"   Looking up '{tool_name}' in namespace '{namespace}':")

                try:
                    found_tool = await registry.get_tool(tool_name, namespace)
                    if found_tool:
                        print(f"     ✅ Found: {type(found_tool)}")
                    else:
                        print("     ❌ Not found")
                except Exception as e:
                    print(f"     ❌ Exception: {e}")

        else:
            print("❌ No tools found in test namespace!")
            print("\n🔍 Debugging registration process...")

            # Check if tools were registered at all
            print("Available tools by namespace:")
            namespace_tools = {}
            for ns, tool_name in all_tools:
                if ns not in namespace_tools:
                    namespace_tools[ns] = []
                namespace_tools[ns].append(tool_name)

            for ns, tools in namespace_tools.items():
                print(f"   {ns}: {tools}")

        print("\n8️⃣ Registry Implementation Details...")
        print(f"   Registry type: {type(registry)}")
        print(f"   Registry has _tools: {hasattr(registry, '_tools')}")
        print(f"   Registry has _metadata: {hasattr(registry, '_metadata')}")

        if hasattr(registry, "_tools"):
            print(f"   Internal _tools keys: {list(registry._tools.keys())}")
            for ns, tools in registry._tools.items():
                print(f"     {ns}: {list(tools.keys())}")

        # Cleanup
        await stream_manager.close()

    except Exception as e:
        print(f"❌ Diagnostic failed: {e}")
        import traceback

        traceback.print_exc()

    finally:
        # Cleanup config file
        config_path = Path(config_file)
        if config_path.exists():
            config_path.unlink()


async def main():
    """Main diagnostic entry point."""
    await diagnostic_registry_deep_dive()
    print("\n🏁 Registry diagnostic complete!")


if __name__ == "__main__":
    asyncio.run(main())
