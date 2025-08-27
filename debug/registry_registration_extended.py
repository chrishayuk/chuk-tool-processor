#!/usr/bin/env python
"""
Enhanced diagnostic script to test MCP tool registration with additional test scenarios.

ENHANCED VERSION: Includes comprehensive testing for:
1. Tool name collision within same namespace
2. Concurrent registration from multiple sources
3. Large-scale testing (100+ tools, 10+ namespaces)
4. Error recovery testing (server failures during registration)

This script tests:
- Original duplication detection tests
- Tool name collision handling
- Concurrent registration behavior
- Performance under scale
- Resilience to failures

Usage:
    python enhanced_registry_test.py
"""

import asyncio
import json
import os
import signal
import sys
import tempfile
import time
from typing import Any

# Assuming your imports work like this - adjust paths as needed
try:
    from chuk_tool_processor.logging import get_logger
    from chuk_tool_processor.mcp.mcp_tool import MCPTool
    from chuk_tool_processor.mcp.register_mcp_tools import register_mcp_tools
    from chuk_tool_processor.mcp.setup_mcp_stdio import setup_mcp_stdio
    from chuk_tool_processor.mcp.stream_manager import StreamManager
    from chuk_tool_processor.registry.provider import ToolRegistryProvider
except ImportError as e:
    print(f"Import error: {e}")
    print("Please adjust the import paths according to your project structure")
    exit(1)

logger = get_logger("enhanced_registry_test")


class MockStreamManager:
    """Mock StreamManager for testing collision and error scenarios."""

    def __init__(self, tools: list[dict[str, Any]], should_fail: bool = False):
        self.tools = tools
        self.should_fail = should_fail
        self._closed = False

    def get_all_tools(self) -> list[dict[str, Any]]:
        if self.should_fail:
            raise RuntimeError("Mock server failure")
        return self.tools

    async def close(self):
        self._closed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class EnhancedMCPDuplicationTester:
    """Enhanced test suite for MCP tool registration with additional scenarios."""

    def __init__(self):
        self.config_file = None
        self.test_results = {}
        self._shutdown_event = asyncio.Event()
        self.performance_metrics = {}

    async def setup_test_config(self) -> str:
        """Create a temporary config file for testing."""
        config = {
            "mcpServers": {
                "time": {"command": "uvx", "args": ["mcp-server-time", "--local-timezone=America/New_York"]},
                "sqlite": {"command": "uvx", "args": ["mcp-server-sqlite", "--db", "/tmp/mcp_demo.sqlite"]},
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

            return {
                "description": description,
                "total_tools": len(all_tools),
                "namespaces": namespaces,
                "tools_by_namespace": tools_by_namespace,
                "duplicate_counts": duplicate_counts,
                "metadata_count": len(all_metadata),
            }
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
            }

    # ------------------------------------------------------------------ #
    # ORIGINAL TESTS (simplified versions)
    # ------------------------------------------------------------------ #

    async def test_basic_registration(self) -> dict[str, Any]:
        """Test basic single server registration."""
        print("\n=== Testing Basic Registration ===")

        await ToolRegistryProvider.set_registry(None)

        try:
            async with StreamManager.create_managed(
                config_file=self.config_file, servers=["time"], transport_type="stdio", default_timeout=5.0
            ) as stream_manager:
                registered = await register_mcp_tools(stream_manager, namespace="basic_test")
                state = await self.get_registry_state("After basic registration")

                return {"success": True, "state": state, "registered_count": len(registered)}

        except Exception as e:
            logger.error(f"Basic registration test failed: {e}")
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------ #
    # NEW TEST 1: Tool name collision within same namespace
    # ------------------------------------------------------------------ #

    async def test_tool_name_collision(self) -> dict[str, Any]:
        """Test how the registry handles tool name collisions within the same namespace."""
        print("\n=== Testing Tool Name Collision Handling ===")

        await ToolRegistryProvider.set_registry(None)

        try:
            await ToolRegistryProvider.get_registry()
            namespace = "collision_test"

            # Create mock tools with same names but different implementations
            tool1_data = [{"name": "duplicate_tool", "description": "First implementation"}]
            tool2_data = [{"name": "duplicate_tool", "description": "Second implementation"}]

            # Register first tool
            mock_sm1 = MockStreamManager(tool1_data)
            registered1 = await register_mcp_tools(mock_sm1, namespace=namespace)
            await self.get_registry_state("After first tool registration")

            # Try to register second tool with same name
            mock_sm2 = MockStreamManager(tool2_data)
            registered2 = await register_mcp_tools(mock_sm2, namespace=namespace)
            state2 = await self.get_registry_state("After collision registration attempt")

            # Check if collision was handled
            collision_detected = (
                len(registered2) == 0  # Registration rejected
                or state2["duplicate_counts"].get(namespace, {}).get("duplicate_tool", 0) > 1  # Duplicate created
            )

            return {
                "success": True,
                "collision_detected": collision_detected,
                "first_registration": len(registered1),
                "second_registration": len(registered2),
                "final_state": state2,
                "collision_handling": "prevented" if len(registered2) == 0 else "allowed",
            }

        except Exception as e:
            logger.error(f"Tool collision test failed: {e}")
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------ #
    # NEW TEST 2: Concurrent registration from multiple sources
    # ------------------------------------------------------------------ #

    async def test_concurrent_registration(self) -> dict[str, Any]:
        """Test concurrent registration from multiple sources."""
        print("\n=== Testing Concurrent Registration ===")

        await ToolRegistryProvider.set_registry(None)

        try:
            # Create multiple mock stream managers with different tools
            concurrent_tools = [
                [{"name": f"concurrent_tool_{i}", "description": f"Tool from source {i}"}] for i in range(5)
            ]

            namespace = "concurrent_test"
            start_time = time.time()

            # Run concurrent registrations
            async def register_concurrent(tools, source_id):
                mock_sm = MockStreamManager(tools)
                try:
                    registered = await register_mcp_tools(mock_sm, namespace=namespace)
                    return {"source": source_id, "registered": len(registered), "success": True}
                except Exception as e:
                    return {"source": source_id, "registered": 0, "success": False, "error": str(e)}

            # Execute all registrations concurrently
            results = await asyncio.gather(
                *[register_concurrent(tools, i) for i, tools in enumerate(concurrent_tools)], return_exceptions=True
            )

            concurrent_time = time.time() - start_time

            # Get final state
            final_state = await self.get_registry_state("After concurrent registration")

            # Analyze results
            successful_registrations = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
            total_tools_registered = sum(r.get("registered", 0) for r in results if isinstance(r, dict))

            return {
                "success": True,
                "concurrent_sources": len(concurrent_tools),
                "successful_registrations": successful_registrations,
                "total_tools_registered": total_tools_registered,
                "execution_time": concurrent_time,
                "final_state": final_state,
                "results": results,
            }

        except Exception as e:
            logger.error(f"Concurrent registration test failed: {e}")
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------ #
    # NEW TEST 3: Large-scale testing (100+ tools, 10+ namespaces)
    # ------------------------------------------------------------------ #

    async def test_large_scale_registration(self) -> dict[str, Any]:
        """Test registry performance with large numbers of tools and namespaces."""
        print("\n=== Testing Large-Scale Registration ===")

        await ToolRegistryProvider.set_registry(None)

        try:
            start_time = time.time()

            # Generate large dataset
            num_namespaces = 12
            tools_per_namespace = 10
            total_expected_tools = num_namespaces * tools_per_namespace

            print(f"Registering {total_expected_tools} tools across {num_namespaces} namespaces...")

            registration_times = []

            for ns_id in range(num_namespaces):
                namespace = f"scale_test_ns_{ns_id}"

                # Create tools for this namespace
                tools_data = [
                    {
                        "name": f"tool_{ns_id}_{tool_id}",
                        "description": f"Tool {tool_id} in namespace {ns_id}",
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                    for tool_id in range(tools_per_namespace)
                ]

                # Register tools and measure time
                ns_start = time.time()
                mock_sm = MockStreamManager(tools_data)
                await register_mcp_tools(mock_sm, namespace=namespace)
                ns_time = time.time() - ns_start

                registration_times.append(ns_time)

                if ns_id % 3 == 0:  # Progress indicator
                    print(f"  Completed namespace {ns_id + 1}/{num_namespaces}")

            total_time = time.time() - start_time

            # Get final state and analyze performance
            final_state = await self.get_registry_state("After large-scale registration")

            # Performance metrics
            avg_registration_time = sum(registration_times) / len(registration_times)
            tools_per_second = total_expected_tools / total_time

            self.performance_metrics["large_scale"] = {
                "total_tools": total_expected_tools,
                "actual_tools": final_state["total_tools"],
                "total_time": total_time,
                "avg_ns_time": avg_registration_time,
                "tools_per_second": tools_per_second,
            }

            return {
                "success": True,
                "expected_tools": total_expected_tools,
                "actual_tools": final_state["total_tools"],
                "expected_namespaces": num_namespaces,
                "actual_namespaces": len(final_state["namespaces"]),
                "total_time": total_time,
                "avg_registration_time": avg_registration_time,
                "tools_per_second": tools_per_second,
                "performance_grade": "excellent"
                if tools_per_second > 50
                else "good"
                if tools_per_second > 20
                else "needs_optimization",
                "final_state": final_state,
            }

        except Exception as e:
            logger.error(f"Large-scale test failed: {e}")
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------ #
    # NEW TEST 4: Error recovery testing (server failures during registration)
    # ------------------------------------------------------------------ #

    async def test_error_recovery(self) -> dict[str, Any]:
        """Test registry behavior when servers fail during registration."""
        print("\n=== Testing Error Recovery ===")

        await ToolRegistryProvider.set_registry(None)

        try:
            namespace = "error_recovery_test"

            # Test 1: Registration with failing server
            print("  Testing registration with failing server...")
            failing_sm = MockStreamManager([], should_fail=True)

            try:
                failed_registration = await register_mcp_tools(failing_sm, namespace=namespace)
                failure_handled = True
                failure_error = None
            except Exception as e:
                failure_handled = True
                failure_error = str(e)
                failed_registration = []

            await self.get_registry_state("After failed registration")

            # Test 2: Successful registration after failure
            print("  Testing recovery with successful registration...")
            success_tools = [
                {"name": "recovery_tool_1", "description": "Tool after failure"},
                {"name": "recovery_tool_2", "description": "Another recovery tool"},
            ]
            recovery_sm = MockStreamManager(success_tools)
            recovery_registration = await register_mcp_tools(recovery_sm, namespace=namespace)

            state_after_recovery = await self.get_registry_state("After recovery registration")

            # Test 3: Mixed success/failure scenario
            print("  Testing mixed success/failure scenario...")
            mixed_results = []

            # Multiple registrations with some failures
            for i in range(5):
                should_fail = i % 3 == 0  # Fail every 3rd registration
                tools = [{"name": f"mixed_tool_{i}", "description": f"Mixed tool {i}"}] if not should_fail else []
                mock_sm = MockStreamManager(tools, should_fail=should_fail)

                try:
                    registered = await register_mcp_tools(mock_sm, namespace=f"{namespace}_mixed_{i}")
                    mixed_results.append({"index": i, "success": True, "registered": len(registered)})
                except Exception as e:
                    mixed_results.append({"index": i, "success": False, "error": str(e)})

            final_state = await self.get_registry_state("After mixed scenario")

            # Analyze error recovery
            successful_recoveries = sum(1 for r in mixed_results if r["success"])
            failed_attempts = sum(1 for r in mixed_results if not r["success"])

            return {
                "success": True,
                "failure_handling": {
                    "failure_handled_gracefully": failure_handled,
                    "failure_error": failure_error,
                    "tools_registered_despite_failure": len(failed_registration),
                },
                "recovery_behavior": {
                    "recovery_successful": len(recovery_registration) > 0,
                    "tools_after_recovery": len(recovery_registration),
                    "registry_state_clean": len(state_after_recovery["namespaces"]) > 0,
                },
                "mixed_scenario": {
                    "total_attempts": len(mixed_results),
                    "successful_recoveries": successful_recoveries,
                    "failed_attempts": failed_attempts,
                    "success_rate": successful_recoveries / len(mixed_results) * 100,
                },
                "final_state": final_state,
                "resilience_grade": "excellent" if successful_recoveries > failed_attempts else "good",
            }

        except Exception as e:
            logger.error(f"Error recovery test failed: {e}")
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------ #
    # Analysis and reporting
    # ------------------------------------------------------------------ #

    def analyze_enhanced_results(self, test_results: dict[str, Any]):
        """Analyze all test results including the new enhanced tests."""
        print("\n" + "=" * 60)
        print("=== ENHANCED REGISTRY TEST ANALYSIS ===")
        print("=" * 60)

        issues_found = []
        insights = []

        for test_name, result in test_results.items():
            if not result.get("success"):
                print(f"\n❌ {test_name.upper()}: FAILED")
                print(f"   Error: {result.get('error', 'Unknown error')}")
                continue

            print(f"\n✅ {test_name.upper()}: PASSED")

            # Analyze specific test types
            if test_name == "basic_registration":
                print(f"   📊 Registered {result['registered_count']} tools successfully")

            elif test_name == "tool_name_collision":
                collision_handling = result.get("collision_handling", "unknown")
                print(f"   🔍 Collision handling: {collision_handling}")
                print(f"   📝 First registration: {result['first_registration']} tools")
                print(f"   📝 Second registration: {result['second_registration']} tools")

                if collision_handling == "allowed":
                    insights.append("Registry allows tool name collisions within namespaces")
                else:
                    insights.append("Registry prevents tool name collisions within namespaces")

            elif test_name == "concurrent_registration":
                success_rate = result["successful_registrations"] / result["concurrent_sources"] * 100
                print(f"   ⚡ Concurrent sources: {result['concurrent_sources']}")
                print(f"   ✅ Success rate: {success_rate:.1f}%")
                print(f"   🏃 Execution time: {result['execution_time']:.3f}s")
                print(f"   📊 Total tools: {result['total_tools_registered']}")

                if success_rate == 100:
                    insights.append("Registry handles concurrent registration perfectly")
                elif success_rate > 80:
                    insights.append("Registry handles concurrent registration well")
                else:
                    issues_found.append("Registry has issues with concurrent registration")

            elif test_name == "large_scale_registration":
                print(f"   📈 Scale: {result['actual_tools']} tools, {result['actual_namespaces']} namespaces")
                print(f"   ⏱️  Performance: {result['tools_per_second']:.1f} tools/second")
                print(f"   🎯 Grade: {result['performance_grade']}")

                if result["performance_grade"] == "excellent":
                    insights.append("Registry scales excellently for large datasets")
                elif result["performance_grade"] == "good":
                    insights.append("Registry scales well for large datasets")
                else:
                    issues_found.append("Registry performance needs optimization for scale")

            elif test_name == "error_recovery":
                recovery = result["recovery_behavior"]
                mixed = result["mixed_scenario"]
                print(
                    f"   🛡️  Failure handling: {'✅ Graceful' if result['failure_handling']['failure_handled_gracefully'] else '❌ Poor'}"
                )
                print(f"   🔄 Recovery success: {'✅ Yes' if recovery['recovery_successful'] else '❌ No'}")
                print(f"   📊 Mixed scenario success rate: {mixed['success_rate']:.1f}%")
                print(f"   🏆 Resilience grade: {result['resilience_grade']}")

                if result["resilience_grade"] == "excellent":
                    insights.append("Registry demonstrates excellent error resilience")
                else:
                    insights.append("Registry shows good error recovery capabilities")

        # Print summary
        print("\n" + "=" * 60)
        print("=== SUMMARY ===")
        print("=" * 60)

        if issues_found:
            print(f"⚠️  {len(issues_found)} issues found:")
            for issue in issues_found:
                print(f"   • {issue}")
        else:
            print("✅ No critical issues found!")

        if insights:
            print("\n🧠 Key insights:")
            for insight in insights:
                print(f"   • {insight}")

        # Performance summary
        if "large_scale" in self.performance_metrics:
            perf = self.performance_metrics["large_scale"]
            print("\n📊 Performance Summary:")
            print(f"   • Registry processed {perf['total_tools']} tools in {perf['total_time']:.2f}s")
            print(f"   • Average rate: {perf['tools_per_second']:.1f} tools/second")
            print(f"   • Memory efficiency: {perf['actual_tools'] == perf['total_tools']}")

        return issues_found

    async def run_all_enhanced_tests(self) -> dict[str, Any]:
        """Run all tests including the new enhanced scenarios."""
        print("Starting Enhanced MCP Registry Tests...")
        print("This will test collision handling, concurrency, scale, and error recovery.")

        await self.setup_test_config()

        try:
            test_results = {}

            # Define test suite
            tests = [
                ("basic_registration", self.test_basic_registration),
                ("tool_name_collision", self.test_tool_name_collision),
                ("concurrent_registration", self.test_concurrent_registration),
                ("large_scale_registration", self.test_large_scale_registration),
                ("error_recovery", self.test_error_recovery),
            ]

            # Run each test
            for test_name, test_func in tests:
                if self._shutdown_event.is_set():
                    logger.info("Shutdown requested, stopping tests")
                    break

                logger.info(f"Running enhanced test: {test_name}")
                test_start = time.time()

                test_results[test_name] = await test_func()

                test_time = time.time() - test_start
                print(f"   Completed in {test_time:.2f}s")

                # Brief pause between tests
                await asyncio.sleep(0.1)

            # Analyze all results
            issues = self.analyze_enhanced_results(test_results)

            return {
                "test_results": test_results,
                "issues_found": issues,
                "performance_metrics": self.performance_metrics,
                "success": len(issues) == 0,
                "test_summary": {
                    "total_tests": len(tests),
                    "completed_tests": len(test_results),
                    "passed_tests": sum(1 for r in test_results.values() if r.get("success")),
                    "failed_tests": sum(1 for r in test_results.values() if not r.get("success")),
                },
            }

        finally:
            self.cleanup()


async def main():
    """Run the enhanced MCP registry tests."""

    # Set up graceful shutdown
    shutdown_event = asyncio.Event()

    def signal_handler():
        logger.info("Received shutdown signal, cleaning up...")
        shutdown_event.set()

    # Register signal handlers
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda s, f: signal_handler())
    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, lambda s, f: signal_handler())

    tester = EnhancedMCPDuplicationTester()
    tester._shutdown_event = shutdown_event

    try:
        # Run enhanced tests with timeout
        results = await asyncio.wait_for(
            tester.run_all_enhanced_tests(),
            timeout=300.0,  # 5 minutes total timeout
        )

        # Save detailed results
        output_file = "enhanced_registry_test_results.json"
        try:
            with open(output_file, "w") as f:
                json.dump(results, f, indent=2, default=str)
            print(f"\n📁 Detailed results saved to: {output_file}")
        except Exception as e:
            print(f"⚠️  Warning: Could not save results to file: {e}")

        # Final summary
        summary = results["test_summary"]
        print("\n🏁 Test Suite Complete:")
        print(f"   📊 {summary['passed_tests']}/{summary['total_tests']} tests passed")

        if results["success"]:
            print("🎉 All enhanced tests passed - registry is robust and scalable!")
            return 0
        else:
            print(f"⚠️  Found {len(results['issues_found'])} issues that need attention")
            return 1

    except TimeoutError:
        logger.error("Enhanced tests timed out after 5 minutes")
        print("❌ Tests timed out")
        return 1
    except KeyboardInterrupt:
        logger.info("Enhanced tests interrupted by user")
        print("⚠️ Tests interrupted")
        return 130
    except Exception as e:
        logger.error(f"Enhanced test execution failed: {e}")
        print(f"❌ Test execution failed: {e}")
        return 1


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
