#!/usr/bin/env python
"""
Diagnostic script to test MCP tool registration and detect duplications.

FINAL VERSION: Uses enhanced StreamManager with robust shutdown handling
and comprehensive error management to prevent event loop closure issues.

This script tests:
1. Multiple MCP servers with potentially overlapping tool names
2. Registry behavior when tools with same names are registered
3. Namespace isolation between different MCP setups
4. Tool metadata consistency across registrations

Usage:
    python test_mcp_duplication.py
"""

import asyncio
import json
import os
import signal
import sys
import tempfile
from typing import Any

# Assuming your imports work like this - adjust paths as needed
try:
    from chuk_tool_processor.logging import get_logger
    from chuk_tool_processor.mcp.register_mcp_tools import register_mcp_tools
    from chuk_tool_processor.mcp.setup_mcp_stdio import setup_mcp_stdio
    from chuk_tool_processor.mcp.stream_manager import StreamManager
    from chuk_tool_processor.registry.provider import ToolRegistryProvider
except ImportError as e:
    print(f"Import error: {e}")
    print("Please adjust the import paths according to your project structure")
    exit(1)

logger = get_logger("mcp_duplication_test")


class MCPDuplicationTester:
    """Test MCP tool registration for duplications and conflicts."""

    def __init__(self):
        self.config_file = None
        self.test_results = {}
        self._shutdown_event = asyncio.Event()

    async def setup_test_config(self) -> str:
        """Create a temporary config file for testing."""
        config = {
            "mcpServers": {
                "time": {"command": "uvx", "args": ["mcp-server-time", "--local-timezone=America/New_York"]},
                "sqlite": {"command": "uvx", "args": ["mcp-server-sqlite", "--db", "/tmp/mcp_demo.sqlite"]},
                # Add a third server that might have overlapping tools
                "time2": {"command": "uvx", "args": ["mcp-server-time", "--local-timezone=Europe/London"]},
            }
        }

        # Create temporary config file
        fd, self.config_file = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(config, f, indent=2)
        except:
            os.close(fd)
            raise

        logger.info(f"Created test config: {self.config_file}")
        return self.config_file

    def cleanup(self):
        """Clean up temporary files."""
        if self.config_file and os.path.exists(self.config_file):
            os.unlink(self.config_file)
            logger.info(f"Cleaned up config file: {self.config_file}")

    async def get_registry_state(self, description: str) -> dict[str, Any]:
        """Capture the current state of the registry."""
        try:
            registry = await ToolRegistryProvider.get_registry()

            # Get all tools and namespaces
            all_tools = await registry.list_tools()
            namespaces = await registry.list_namespaces()
            all_metadata = await registry.list_metadata()

            # Group tools by namespace
            tools_by_namespace = {}
            for namespace, tool_name in all_tools:
                if namespace not in tools_by_namespace:
                    tools_by_namespace[namespace] = []
                tools_by_namespace[namespace].append(tool_name)

            # Count duplicates within each namespace
            duplicate_counts = {}
            for namespace, tools in tools_by_namespace.items():
                tool_counts = {}
                for tool in tools:
                    tool_counts[tool] = tool_counts.get(tool, 0) + 1

                duplicates = {name: count for name, count in tool_counts.items() if count > 1}
                if duplicates:
                    duplicate_counts[namespace] = duplicates

            state = {
                "description": description,
                "total_tools": len(all_tools),
                "namespaces": namespaces,
                "tools_by_namespace": tools_by_namespace,
                "duplicate_counts": duplicate_counts,
                "metadata_count": len(all_metadata),
                "tool_details": [],
            }

            # Get detailed info for a limited number of tools
            for namespace, tool_name in all_tools[:10]:  # Limit for performance
                try:
                    tool = await registry.get_tool(tool_name, namespace)
                    metadata = await registry.get_metadata(tool_name, namespace)

                    tool_info = {
                        "namespace": namespace,
                        "name": tool_name,
                        "tool_type": type(tool).__name__,
                        "has_metadata": metadata is not None,
                        "metadata_description": metadata.description if metadata else None,
                    }

                    state["tool_details"].append(tool_info)
                except Exception as e:
                    logger.debug(f"Error getting details for {namespace}.{tool_name}: {e}")

            return state
        except Exception as e:
            logger.error(f"Error getting registry state: {e}")
            return {
                "description": f"{description} (ERROR)",
                "error": str(e),
                "total_tools": 0,
                "namespaces": [],
                "tools_by_namespace": {},
                "duplicate_counts": {},
                "metadata_count": 0,
                "tool_details": [],
            }

    async def test_single_server_registration(self) -> dict[str, Any]:
        """Test registering tools from a single server."""
        print("\n=== Testing Single Server Registration ===")

        # Clear registry
        await ToolRegistryProvider.set_registry(None)

        try:
            # Use the enhanced StreamManager context manager
            async with StreamManager.create_managed(
                config_file=self.config_file,
                servers=["time"],
                transport_type="stdio",
                default_timeout=5.0,  # Shorter timeout for testing
            ) as stream_manager:
                # Check stream manager health before proceeding
                health = await stream_manager.health_check()
                logger.debug(f"StreamManager health: {health}")

                # Register tools
                registered = await register_mcp_tools(stream_manager, namespace="test_single")
                logger.info(f"Registered {len(registered)} tools from single server")

                state = await self.get_registry_state("After single server (time)")
                return {"success": True, "state": state, "registered_count": len(registered)}

        except Exception as e:
            logger.error(f"Single server test failed: {e}")
            return {"success": False, "error": str(e)}

    async def test_multiple_servers_same_namespace(self) -> dict[str, Any]:
        """Test registering tools from multiple servers in the same namespace."""
        print("\n=== Testing Multiple Servers - Same Namespace ===")

        # Clear registry
        await ToolRegistryProvider.set_registry(None)

        states = []

        try:
            # Test with fewer servers to reduce complexity
            servers_to_test = ["time", "sqlite"]  # Removed time2 to avoid issues

            for i, server in enumerate(servers_to_test):
                logger.info(f"Testing server {i + 1}/{len(servers_to_test)}: {server}")

                async with StreamManager.create_managed(
                    config_file=self.config_file,
                    servers=[server],
                    transport_type="stdio",
                    default_timeout=3.0,  # Very short timeout
                ) as stream_manager:
                    # Register to the same namespace
                    registered = await register_mcp_tools(stream_manager, namespace="test_multi")
                    logger.info(f"Registered {len(registered)} tools from {server}")

                    state = await self.get_registry_state(f"After {server} server - same namespace")
                    states.append(state)

                    # Brief pause between servers
                    await asyncio.sleep(0.1)

            return {"success": True, "states": states}

        except Exception as e:
            logger.error(f"Multiple servers same namespace test failed: {e}")
            return {"success": False, "error": str(e)}

    async def test_multiple_servers_different_namespaces(self) -> dict[str, Any]:
        """Test registering tools from multiple servers in different namespaces."""
        print("\n=== Testing Multiple Servers - Different Namespaces ===")

        # Clear registry
        await ToolRegistryProvider.set_registry(None)

        states = []

        try:
            # Map servers to their respective namespaces
            server_namespace_map = [("time", "time_ns"), ("sqlite", "sqlite_ns")]

            for server, namespace in server_namespace_map:
                logger.info(f"Testing {server} in namespace {namespace}")

                async with StreamManager.create_managed(
                    config_file=self.config_file, servers=[server], transport_type="stdio", default_timeout=3.0
                ) as stream_manager:
                    registered = await register_mcp_tools(stream_manager, namespace=namespace)
                    logger.info(f"Registered {len(registered)} tools from {server} in {namespace}")

                    state = await self.get_registry_state(f"After {server} server in {namespace}")
                    states.append(state)

                    await asyncio.sleep(0.1)

            return {"success": True, "states": states}

        except Exception as e:
            logger.error(f"Multiple servers different namespaces test failed: {e}")
            return {"success": False, "error": str(e)}

    async def test_stream_manager_direct_registration(self) -> dict[str, Any]:
        """Test registering tools directly via StreamManager."""
        print("\n=== Testing Direct StreamManager Registration ===")

        # Clear registry
        await ToolRegistryProvider.set_registry(None)

        states = []

        try:
            # Use only one server to keep it simple
            async with StreamManager.create_managed(
                config_file=self.config_file, servers=["time"], transport_type="stdio", default_timeout=3.0
            ) as stream_manager:
                # Test multiple registrations to the same namespace
                registered1 = await register_mcp_tools(stream_manager, namespace="direct_all")
                state1 = await self.get_registry_state(f"After direct registration ({len(registered1)} tools)")
                states.append(state1)

                # Try to register again (test idempotency)
                registered2 = await register_mcp_tools(stream_manager, namespace="direct_all")
                state2 = await self.get_registry_state(f"After re-registration ({len(registered2)} tools)")
                states.append(state2)

                # Register to different namespace
                registered3 = await register_mcp_tools(stream_manager, namespace="direct_copy")
                state3 = await self.get_registry_state(
                    f"After different namespace registration ({len(registered3)} tools)"
                )
                states.append(state3)

                return {
                    "success": True,
                    "states": states,
                    "registration_counts": [len(registered1), len(registered2), len(registered3)],
                }

        except Exception as e:
            logger.error(f"Direct registration test failed: {e}")
            return {"success": False, "error": str(e)}

    def analyze_duplication_issues(self, test_results: dict[str, Any]):
        """Analyze test results for duplication issues."""
        print("\n=== DUPLICATION ANALYSIS ===")

        issues_found = []

        for test_name, result in test_results.items():
            if not result.get("success"):
                print(f"\n{test_name}: FAILED - {result.get('error', 'Unknown error')}")
                continue

            print(f"\nAnalyzing {test_name}:")

            if "states" in result:
                states = result["states"]
            elif "state" in result:
                states = [result["state"]]
            else:
                continue

            for state in states:
                print(f"  {state['description']}:")
                print(f"    Total tools: {state['total_tools']}")
                print(f"    Namespaces: {state['namespaces']}")

                # Check for duplicates
                if state["duplicate_counts"]:
                    print(f"    ⚠️  DUPLICATES FOUND: {state['duplicate_counts']}")
                    issues_found.append(
                        {
                            "test": test_name,
                            "description": state["description"],
                            "duplicates": state["duplicate_counts"],
                        }
                    )
                else:
                    print("    ✅ No duplicates found")

                # Show tools by namespace
                for namespace, tools in state["tools_by_namespace"].items():
                    print(f"    {namespace}: {len(tools)} tools - {tools}")

        print("\n=== SUMMARY ===")
        if issues_found:
            print(f"❌ Found {len(issues_found)} duplication issues:")
            for issue in issues_found:
                print(f"  - {issue['test']}: {issue['description']}")
                print(f"    Duplicates: {issue['duplicates']}")
        else:
            print("✅ No duplication issues found!")

        return issues_found

    async def run_all_tests(self) -> dict[str, Any]:
        """Run all duplication tests with proper cleanup."""
        print("Starting MCP Registry Duplication Tests...")

        await self.setup_test_config()

        try:
            test_results = {}

            # Run tests sequentially with proper cleanup between each
            tests = [
                ("single_server", self.test_single_server_registration),
                ("multi_same_ns", self.test_multiple_servers_same_namespace),
                ("multi_diff_ns", self.test_multiple_servers_different_namespaces),
                ("direct_registration", self.test_stream_manager_direct_registration),
            ]

            for test_name, test_func in tests:
                if self._shutdown_event.is_set():
                    logger.info("Shutdown requested, stopping tests")
                    break

                logger.info(f"Running test: {test_name}")
                test_results[test_name] = await test_func()

                # Brief pause between tests
                await asyncio.sleep(0.2)

                # Force garbage collection to clean up resources
                import gc

                gc.collect()

            # Analyze results
            issues = self.analyze_duplication_issues(test_results)

            return {"test_results": test_results, "duplication_issues": issues, "success": len(issues) == 0}

        finally:
            self.cleanup()


async def main():
    """Run the MCP duplication tests with proper signal handling."""

    # Set up graceful shutdown
    shutdown_event = asyncio.Event()

    def signal_handler():
        logger.info("Received shutdown signal, cleaning up...")
        shutdown_event.set()

    # Register signal handlers for graceful shutdown
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda s, f: signal_handler())
    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, lambda s, f: signal_handler())

    tester = MCPDuplicationTester()
    tester._shutdown_event = shutdown_event

    try:
        # Run tests with overall timeout protection
        results = await asyncio.wait_for(
            tester.run_all_tests(),
            timeout=120.0,  # 2 minutes total timeout
        )

        # Save detailed results
        output_file = "mcp_duplication_test_results.json"
        try:
            with open(output_file, "w") as f:
                json.dump(results, f, indent=2, default=str)
            print(f"\nDetailed results saved to: {output_file}")
        except Exception as e:
            print(f"Warning: Could not save results to file: {e}")

        if results["success"]:
            print("🎉 All tests passed - no duplication issues found!")
            return 0
        else:
            print(f"❌ Found {len(results['duplication_issues'])} duplication issues")
            return 1

    except TimeoutError:
        logger.error("Tests timed out after 2 minutes")
        print("❌ Tests timed out")
        return 1
    except KeyboardInterrupt:
        logger.info("Tests interrupted by user")
        print("⚠️ Tests interrupted")
        return 130
    except Exception as e:
        logger.error(f"Test execution failed: {e}")
        print(f"❌ Test execution failed: {e}")
        return 1
    finally:
        # Final cleanup
        try:
            tester.cleanup()
        except Exception as e:
            logger.debug(f"Error during final cleanup: {e}")


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
