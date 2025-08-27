#!/usr/bin/env python
"""
resilience_stdio_demo.py - FIXED VERSION
─────────────────────────────────────
FIXED: Tool naming issue resolved. The issue was that tools are registered
with their original names (e.g., "get_current_time") but the test was trying
to access them with namespaced names (e.g., "resilience_test.get_current_time").

This version:
1. Uses correct tool names from the registry
2. Adds registry inspection to find available tools
3. Provides better error diagnostics
4. Handles tool discovery dynamically
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil
from colorama import Fore, Style
from colorama import init as colorama_init

colorama_init(autoreset=True)

# ─── local-package bootstrap ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.mcp.setup_mcp_stdio import setup_mcp_stdio
from chuk_tool_processor.mcp.stream_manager import StreamManager
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.registry.provider import ToolRegistryProvider

logger = get_logger("mcp-resilience-test")

# ═══════════════════════════════════════════════════════════════════════════
# Resilience Test Configuration
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ResilienceTestConfig:
    """Configuration for resilience testing scenarios."""

    max_test_duration: float = 300.0  # 5 minutes max per test
    connection_retry_attempts: int = 3
    retry_delay: float = 1.0
    stress_test_calls: int = 20  # Reduced for more reliable testing
    concurrent_connections: int = 3  # Reduced for stability
    failure_injection_rate: float = 0.3  # 30% of operations will fail
    server_restart_delay: float = 2.0
    timeout_test_duration: float = 10.0


@dataclass
class TestResult:
    """Result of a resilience test."""

    test_name: str
    success: bool
    duration: float
    error_count: int = 0
    recovery_count: int = 0
    total_operations: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if self.total_operations == 0:
            return 0.0
        return (self.total_operations - self.error_count) / self.total_operations * 100


class MCPResilienceTestSuite:
    """Comprehensive resilience testing suite for MCP tools."""

    def __init__(self, config: ResilienceTestConfig):
        self.config = config
        self.config_file = PROJECT_ROOT / "resilience_test_config.json"
        self.test_results: list[TestResult] = []
        self.shutdown_event = asyncio.Event()
        self.stream_managers: list[StreamManager] = []
        self.available_tools: dict[str, list[str]] = {}  # namespace -> [tool_names]

    async def setup_test_environment(self):
        """Set up the test environment with MCP servers."""
        # Create config for multiple servers for redundancy testing
        test_config = {
            "mcpServers": {
                "time_primary": {"command": "uvx", "args": ["mcp-server-time", "--local-timezone=America/New_York"]},
                "time_secondary": {"command": "uvx", "args": ["mcp-server-time", "--local-timezone=Europe/London"]},
                "sqlite_test": {"command": "uvx", "args": ["mcp-server-sqlite", "--db", "/tmp/resilience_test.sqlite"]},
            }
        }

        self.config_file.write_text(json.dumps(test_config, indent=2))
        logger.info(f"Created resilience test config: {self.config_file}")

    def cleanup_test_environment(self):
        """Clean up test environment."""
        if self.config_file.exists():
            self.config_file.unlink()
            logger.info("Cleaned up test config file")

    def banner(self, text: str, color: str = Fore.CYAN) -> None:
        """Print a colored banner."""
        print(f"\n{color}{'=' * 60}")
        print(f"  {text}")
        print(f"{'=' * 60}{Style.RESET_ALL}\n")

    def print_progress(self, message: str, color: str = Fore.YELLOW):
        """Print progress message."""
        print(f"{color}🔄 {message}{Style.RESET_ALL}")

    async def discover_available_tools(self, namespace: str) -> list[str]:
        """FIXED: Discover what tools are actually available in the registry."""
        try:
            registry = await ToolRegistryProvider.get_registry()
            all_tools = await registry.list_tools()

            # Filter tools for the specific namespace
            namespace_tools = [tool_name for ns, tool_name in all_tools if ns == namespace]

            self.print_progress(f"Found {len(namespace_tools)} tools in namespace '{namespace}': {namespace_tools}")
            self.available_tools[namespace] = namespace_tools

            return namespace_tools

        except Exception as e:
            logger.error(f"Error discovering tools in namespace {namespace}: {e}")
            return []

    async def wait_with_timeout(self, coro, timeout: float, test_name: str):
        """Execute coroutine with timeout and proper error handling."""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except TimeoutError:
            logger.warning(f"{test_name} timed out after {timeout}s")
            return None
        except Exception as e:
            logger.error(f"{test_name} failed: {e}")
            return None

    # ================================================================
    # Test 1: Basic Connection Recovery - FIXED
    # ================================================================

    async def test_basic_connection_recovery(self) -> TestResult:
        """Test basic connection loss and recovery."""
        self.banner("TEST 1: Basic Connection Recovery", Fore.GREEN)

        start_time = time.time()
        test_result = TestResult("basic_connection_recovery", False, 0.0)

        try:
            self.print_progress("Setting up initial connection...")

            # Set up initial connection
            processor, stream_manager = await setup_mcp_stdio(
                config_file=str(self.config_file),
                servers=["time_primary"],
                namespace="resilience_test",
                default_timeout=5.0,
            )
            self.stream_managers.append(stream_manager)

            # FIXED: Discover available tools
            available_tools = await self.discover_available_tools("resilience_test")
            if not available_tools:
                raise RuntimeError("No tools found in resilience_test namespace")

            # Use the first available tool (should be get_current_time)
            test_tool = available_tools[0]
            self.print_progress(f"Using tool: {test_tool}")

            registry = await ToolRegistryProvider.get_registry()
            executor = ToolExecutor(registry, strategy=InProcessStrategy(registry, default_timeout=5.0))

            # Test initial connectivity with correct tool name
            self.print_progress("Testing initial connectivity...")
            initial_call = ToolCall(
                tool=test_tool,  # FIXED: Use actual tool name, not namespaced
                arguments={"timezone": "UTC"} if "time" in test_tool else {},
            )

            initial_result = await executor.execute([initial_call])
            test_result.total_operations += 1

            if initial_result[0].error:
                raise RuntimeError(f"Initial connectivity test failed: {initial_result[0].error}")

            self.print_progress("✅ Initial connectivity confirmed")

            # Simulate connection loss by closing stream manager
            self.print_progress("Simulating connection loss...")
            await stream_manager.close()

            # Test recovery by creating new connection
            self.print_progress("Testing connection recovery...")
            processor2, stream_manager2 = await setup_mcp_stdio(
                config_file=str(self.config_file),
                servers=["time_primary"],
                namespace="resilience_test",
                default_timeout=5.0,
            )
            self.stream_managers.append(stream_manager2)

            # Give some time for registration
            await asyncio.sleep(1.0)

            # Rediscover tools after reconnection
            recovery_tools = await self.discover_available_tools("resilience_test")
            if test_tool in recovery_tools:
                # Test connectivity after recovery
                recovery_call = ToolCall(tool=test_tool, arguments={"timezone": "UTC"} if "time" in test_tool else {})

                recovery_result = await executor.execute([recovery_call])
                test_result.total_operations += 1

                if not recovery_result[0].error:
                    test_result.recovery_count += 1
                    self.print_progress("✅ Connection recovery successful!")
                    test_result.success = True
                else:
                    self.print_progress(f"❌ Recovery failed: {recovery_result[0].error}")
            else:
                self.print_progress(f"❌ Tool {test_tool} not available after recovery")

        except Exception as e:
            logger.error(f"Basic connection recovery test failed: {e}")
            test_result.details["error"] = str(e)

        finally:
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)

        return test_result

    # ================================================================
    # Test 2: Server Process Recovery - FIXED
    # ================================================================

    async def test_server_process_recovery(self) -> TestResult:
        """Test recovery from server process crashes."""
        self.banner("TEST 2: Server Process Recovery", Fore.GREEN)

        start_time = time.time()
        test_result = TestResult("server_process_recovery", False, 0.0)

        try:
            self.print_progress("Setting up server connection...")

            processor, stream_manager = await setup_mcp_stdio(
                config_file=str(self.config_file),
                servers=["time_primary"],
                namespace="process_recovery",
                default_timeout=10.0,
            )
            self.stream_managers.append(stream_manager)

            # FIXED: Discover available tools
            available_tools = await self.discover_available_tools("process_recovery")
            if not available_tools:
                raise RuntimeError("No tools found in process_recovery namespace")

            test_tool = available_tools[0]
            self.print_progress(f"Using tool: {test_tool}")

            registry = await ToolRegistryProvider.get_registry()
            executor = ToolExecutor(registry, strategy=InProcessStrategy(registry, default_timeout=10.0))

            # Test before server "crash"
            self.print_progress("Testing before server crash...")
            pre_crash_call = ToolCall(tool=test_tool, arguments={"timezone": "UTC"} if "time" in test_tool else {})

            pre_result = await executor.execute([pre_crash_call])
            test_result.total_operations += 1

            if pre_result[0].error:
                raise RuntimeError(f"Pre-crash test failed: {pre_result[0].error}")

            self.print_progress("✅ Pre-crash connectivity confirmed")

            # Find and terminate mcp-server-time processes (simulate crash)
            self.print_progress("Simulating server process crash...")
            terminated_pids = []

            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    if "mcp-server-time" in " ".join(proc.info["cmdline"] or []):
                        proc.terminate()
                        terminated_pids.append(proc.info["pid"])
                        self.print_progress(f"Terminated process {proc.info['pid']}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # Wait for processes to die
            await asyncio.sleep(1.0)

            # Test immediately after crash
            self.print_progress("Testing immediately after crash...")
            crash_call = ToolCall(tool=test_tool, arguments={"timezone": "UTC"} if "time" in test_tool else {})

            crash_result = await executor.execute([crash_call])
            test_result.total_operations += 1

            if crash_result[0].error:
                test_result.error_count += 1
                self.print_progress("🔄 Server crash detected (expected)")

            # Try creating entirely new connection for recovery
            self.print_progress("Attempting complete connection restart...")
            try:
                await stream_manager.close()

                # Wait a bit for cleanup
                await asyncio.sleep(2.0)

                processor2, stream_manager2 = await setup_mcp_stdio(
                    config_file=str(self.config_file),
                    servers=["time_primary"],
                    namespace="process_recovery",
                    default_timeout=10.0,
                )
                self.stream_managers.append(stream_manager2)

                await asyncio.sleep(2.0)  # Allow time for startup

                # Check if tools are available again
                recovery_tools = await self.discover_available_tools("process_recovery")
                if test_tool in recovery_tools:
                    final_call = ToolCall(tool=test_tool, arguments={"timezone": "UTC"} if "time" in test_tool else {})

                    final_result = await executor.execute([final_call])
                    test_result.total_operations += 1

                    if not final_result[0].error:
                        test_result.recovery_count += 1
                        test_result.success = True
                        self.print_progress("✅ Complete restart recovery successful!")
                    else:
                        test_result.error_count += 1
                        self.print_progress(f"❌ Recovery call failed: {final_result[0].error}")
                else:
                    self.print_progress(f"❌ Tool {test_tool} not available after restart")

            except Exception as e:
                self.print_progress(f"❌ Complete restart failed: {e}")

        except Exception as e:
            logger.error(f"Server process recovery test failed: {e}")
            test_result.details["error"] = str(e)

        finally:
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)

        return test_result

    # ================================================================
    # Test 3: Network Timeout Recovery - FIXED
    # ================================================================

    async def test_network_timeout_recovery(self) -> TestResult:
        """Test recovery from network timeouts and slow responses."""
        self.banner("TEST 3: Network Timeout Recovery", Fore.GREEN)

        start_time = time.time()
        test_result = TestResult("network_timeout_recovery", False, 0.0)

        try:
            self.print_progress("Setting up connection for timeout testing...")

            processor, stream_manager = await setup_mcp_stdio(
                config_file=str(self.config_file),
                servers=["time_primary"],
                namespace="timeout_test",
                default_timeout=2.0,
            )
            self.stream_managers.append(stream_manager)

            # FIXED: Discover available tools
            available_tools = await self.discover_available_tools("timeout_test")
            if not available_tools:
                raise RuntimeError("No tools found in timeout_test namespace")

            test_tool = available_tools[0]
            self.print_progress(f"Using tool: {test_tool}")

            registry = await ToolRegistryProvider.get_registry()
            executor = ToolExecutor(
                registry,
                strategy=InProcessStrategy(registry, default_timeout=1.0),  # Short timeout
            )

            # Test normal operation first
            self.print_progress("Testing normal operation...")
            normal_call = ToolCall(tool=test_tool, arguments={"timezone": "UTC"} if "time" in test_tool else {})

            normal_result = await executor.execute([normal_call])
            test_result.total_operations += 1

            if normal_result[0].error:
                self.print_progress(f"⚠️ Normal operation failed: {normal_result[0].error}")
                test_result.error_count += 1
            else:
                self.print_progress("✅ Normal operation successful")

            # Test with very short timeouts to potentially force timeout errors
            self.print_progress("Testing with aggressive timeouts...")

            for i in range(3):
                try:
                    call = ToolCall(
                        tool=test_tool, arguments={"timezone": "Invalid/Timezone"} if "time" in test_tool else {}
                    )

                    result = await asyncio.wait_for(
                        executor.execute([call]),
                        timeout=0.1,  # Very aggressive timeout
                    )
                    test_result.total_operations += 1

                    if result[0].error:
                        test_result.error_count += 1
                        self.print_progress(f"Call {i + 1}: Error (expected) - {result[0].error[:50]}...")
                    else:
                        self.print_progress(f"Call {i + 1}: Success (unexpected)")

                except TimeoutError:
                    test_result.total_operations += 1
                    test_result.error_count += 1
                    self.print_progress(f"Call {i + 1}: Timeout (expected)")

            # Test recovery with reasonable timeouts
            self.print_progress("Testing recovery with reasonable timeouts...")

            recovery_executor = ToolExecutor(registry, strategy=InProcessStrategy(registry, default_timeout=10.0))

            for i in range(3):
                recovery_call = ToolCall(tool=test_tool, arguments={"timezone": "UTC"} if "time" in test_tool else {})

                recovery_result = await recovery_executor.execute([recovery_call])
                test_result.total_operations += 1

                if not recovery_result[0].error:
                    test_result.recovery_count += 1
                    self.print_progress(f"Recovery call {i + 1}: ✅ Success")
                else:
                    test_result.error_count += 1
                    self.print_progress(f"Recovery call {i + 1}: ❌ Failed - {recovery_result[0].error}")

            # Test passes if we can recover from timeouts
            if test_result.recovery_count > 0:
                test_result.success = True
                self.print_progress(
                    f"✅ Timeout recovery successful! {test_result.recovery_count}/3 recovery calls succeeded"
                )
            else:
                self.print_progress("❌ No successful recovery calls")

        except Exception as e:
            logger.error(f"Network timeout recovery test failed: {e}")
            test_result.details["error"] = str(e)

        finally:
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)

        return test_result

    # ================================================================
    # Test 4: Concurrent Stress with Failures - FIXED
    # ================================================================

    async def test_concurrent_stress_with_failures(self) -> TestResult:
        """Test system behavior under concurrent load with intermittent failures."""
        self.banner("TEST 4: Concurrent Stress with Failures", Fore.GREEN)

        start_time = time.time()
        test_result = TestResult("concurrent_stress_with_failures", False, 0.0)

        try:
            self.print_progress("Setting up multiple connections for stress testing...")

            # Set up multiple stream managers for redundancy
            stream_managers = []
            servers = ["time_primary", "time_secondary", "sqlite_test"]
            namespaces = []
            all_available_tools = {}

            for i, server in enumerate(servers):
                try:
                    namespace = f"stress_test_{i}"
                    processor, sm = await setup_mcp_stdio(
                        config_file=str(self.config_file), servers=[server], namespace=namespace, default_timeout=5.0
                    )
                    stream_managers.append(sm)
                    self.stream_managers.append(sm)
                    namespaces.append(namespace)

                    # FIXED: Discover tools for each namespace
                    tools = await self.discover_available_tools(namespace)
                    all_available_tools[namespace] = tools

                    self.print_progress(f"✅ Connected to {server} with {len(tools)} tools")
                except Exception as e:
                    self.print_progress(f"⚠️ Failed to connect to {server}: {e}")

            if not stream_managers:
                raise RuntimeError("No connections established for stress test")

            registry = await ToolRegistryProvider.get_registry()
            executor = ToolExecutor(
                registry, strategy=InProcessStrategy(registry, default_timeout=10.0, max_concurrency=10)
            )

            # Generate concurrent calls with mix of valid and potentially problematic calls
            stress_calls = []

            for i in range(self.config.stress_test_calls):
                # Pick a random namespace that has tools
                available_namespaces = [ns for ns, tools in all_available_tools.items() if tools]
                if not available_namespaces:
                    break

                namespace = random.choice(available_namespaces)
                tools = all_available_tools[namespace]
                tool = random.choice(tools)

                # Create appropriate arguments based on tool type
                if "time" in tool:
                    if i % 4 == 0:
                        # Valid timezone
                        args = {"timezone": random.choice(["UTC", "America/New_York", "Europe/London"])}
                    else:
                        # Invalid timezone (should cause errors but not crashes)
                        args = {"timezone": f"Invalid/Timezone_{i}"}
                else:
                    # SQLite tools - use simple empty args
                    args = {}

                call = ToolCall(tool=tool, arguments=args)
                stress_calls.append(call)

            if not stress_calls:
                raise RuntimeError("No stress calls could be generated")

            self.print_progress(f"Executing {len(stress_calls)} concurrent calls...")

            # Execute all calls concurrently
            stress_start = time.time()
            stress_results = await executor.execute(stress_calls)
            stress_duration = time.time() - stress_start

            # Analyze results
            successful_calls = sum(1 for r in stress_results if not r.error)
            failed_calls = len(stress_results) - successful_calls

            test_result.total_operations = len(stress_results)
            test_result.error_count = failed_calls
            test_result.recovery_count = successful_calls

            calls_per_second = len(stress_calls) / stress_duration if stress_duration > 0 else 0

            self.print_progress(f"Stress test completed in {stress_duration:.2f}s")
            self.print_progress(f"Throughput: {calls_per_second:.1f} calls/second")
            self.print_progress(f"Success rate: {test_result.success_rate:.1f}%")
            self.print_progress(f"Successful calls: {successful_calls}")
            self.print_progress(f"Failed calls: {failed_calls}")

            # Test passes if success rate is reasonable (>40%) and no system crashes
            if test_result.success_rate >= 40.0:
                test_result.success = True
                self.print_progress("✅ Stress test passed - system remained stable under load")
            else:
                self.print_progress("❌ Stress test failed - too many failures under load")

            test_result.details.update(
                {
                    "calls_per_second": calls_per_second,
                    "stress_duration": stress_duration,
                    "success_rate": test_result.success_rate,
                    "namespaces_used": list(all_available_tools.keys()),
                    "total_tools_available": sum(len(tools) for tools in all_available_tools.values()),
                }
            )

        except Exception as e:
            logger.error(f"Concurrent stress test failed: {e}")
            test_result.details["error"] = str(e)

        finally:
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)

        return test_result

    # ================================================================
    # Test Runner and Reporting - Same as before
    # ================================================================

    async def run_all_tests(self) -> dict[str, Any]:
        """Run all resilience tests and return comprehensive results."""
        self.banner("MCP RESILIENCE TEST SUITE", Fore.MAGENTA)

        await self.setup_test_environment()

        try:
            # Run all tests
            tests = [
                self.test_basic_connection_recovery,
                self.test_server_process_recovery,
                self.test_network_timeout_recovery,
                self.test_concurrent_stress_with_failures,
            ]

            for test_func in tests:
                if self.shutdown_event.is_set():
                    logger.info("Shutdown requested, stopping tests")
                    break

                try:
                    await asyncio.wait_for(test_func(), timeout=self.config.max_test_duration)

                    # Brief pause between tests
                    await asyncio.sleep(1.0)

                except TimeoutError:
                    logger.error(f"Test {test_func.__name__} timed out after {self.config.max_test_duration}s")
                    timeout_result = TestResult(
                        test_name=test_func.__name__,
                        success=False,
                        duration=self.config.max_test_duration,
                        details={"error": "Test timed out"},
                    )
                    self.test_results.append(timeout_result)

            return self.generate_test_report()

        finally:
            await self.cleanup_connections()
            self.cleanup_test_environment()

    async def cleanup_connections(self):
        """Clean up all stream manager connections."""
        self.print_progress("Cleaning up connections...")

        for sm in self.stream_managers:
            try:
                await asyncio.wait_for(sm.close(), timeout=2.0)
            except (TimeoutError, Exception) as e:
                logger.debug(f"Error closing stream manager: {e}")

        self.stream_managers.clear()

    def generate_test_report(self) -> dict[str, Any]:
        """Generate comprehensive test report."""
        self.banner("RESILIENCE TEST RESULTS", Fore.MAGENTA)

        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r.success)
        failed_tests = total_tests - passed_tests

        total_operations = sum(r.total_operations for r in self.test_results)
        total_errors = sum(r.error_count for r in self.test_results)
        total_recoveries = sum(r.recovery_count for r in self.test_results)

        overall_success_rate = (
            ((total_operations - total_errors) / total_operations * 100) if total_operations > 0 else 0
        )

        # Print summary
        print(f"{Fore.CYAN}📊 TEST SUMMARY:{Style.RESET_ALL}")
        print(f"   Total Tests: {total_tests}")
        print(f"   Passed: {Fore.GREEN}{passed_tests}{Style.RESET_ALL}")
        print(f"   Failed: {Fore.RED}{failed_tests}{Style.RESET_ALL}")
        print(f"   Overall Success Rate: {Fore.YELLOW}{overall_success_rate:.1f}%{Style.RESET_ALL}")
        print(f"   Total Operations: {total_operations}")
        print(f"   Successful Recoveries: {Fore.GREEN}{total_recoveries}{Style.RESET_ALL}")
        print(f"   Errors Handled: {Fore.YELLOW}{total_errors}{Style.RESET_ALL}")

        # Print detailed results
        print(f"\n{Fore.CYAN}📋 DETAILED RESULTS:{Style.RESET_ALL}")
        for result in self.test_results:
            status = f"{Fore.GREEN}✅ PASS" if result.success else f"{Fore.RED}❌ FAIL"
            print(f"   {status}{Style.RESET_ALL} {result.test_name}")
            print(f"      Duration: {result.duration:.2f}s")
            print(f"      Success Rate: {result.success_rate:.1f}%")
            print(
                f"      Operations: {result.total_operations}, Errors: {result.error_count}, Recoveries: {result.recovery_count}"
            )
            if result.details:
                for key, value in result.details.items():
                    if key != "error":
                        print(f"      {key}: {value}")
            if not result.success and "error" in result.details:
                print(f"      {Fore.RED}Error: {result.details['error']}{Style.RESET_ALL}")
            print()

        # Overall assessment
        if passed_tests == total_tests and overall_success_rate >= 80:
            print(f"{Fore.GREEN}🎉 EXCELLENT: All tests passed with good recovery rates!{Style.RESET_ALL}")
            resilience_grade = "excellent"
        elif passed_tests >= total_tests * 0.75 and overall_success_rate >= 60:
            print(f"{Fore.YELLOW}✅ GOOD: Most tests passed with acceptable recovery rates.{Style.RESET_ALL}")
            resilience_grade = "good"
        else:
            print(f"{Fore.RED}⚠️ NEEDS IMPROVEMENT: Some resilience issues detected.{Style.RESET_ALL}")
            resilience_grade = "needs_improvement"

        return {
            "summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "overall_success_rate": overall_success_rate,
                "total_operations": total_operations,
                "total_errors": total_errors,
                "total_recoveries": total_recoveries,
                "resilience_grade": resilience_grade,
            },
            "test_results": [
                {
                    "test_name": r.test_name,
                    "success": r.success,
                    "duration": r.duration,
                    "success_rate": r.success_rate,
                    "total_operations": r.total_operations,
                    "error_count": r.error_count,
                    "recovery_count": r.recovery_count,
                    "details": r.details,
                }
                for r in self.test_results
            ],
            "available_tools_discovered": self.available_tools,
        }


async def main():
    """Main entry point for resilience testing."""
    # Set up logging
    logging.getLogger("chuk_tool_processor").setLevel(getattr(logging, os.environ.get("LOGLEVEL", "INFO").upper()))

    # Set up graceful shutdown
    shutdown_event = asyncio.Event()

    def signal_handler():
        logger.info("Received shutdown signal")
        shutdown_event.set()

    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda s, f: signal_handler())
    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, lambda s, f: signal_handler())

    config = ResilienceTestConfig()
    test_suite = MCPResilienceTestSuite(config)
    test_suite.shutdown_event = shutdown_event

    try:
        print(f"{Fore.MAGENTA}🧪 Starting FIXED MCP Resilience Test Suite...{Style.RESET_ALL}")
        print(
            f"{Fore.YELLOW}This will test connection recovery, server crashes, timeouts, and concurrent stress.{Style.RESET_ALL}"
        )
        print(
            f"{Fore.YELLOW}FIXED: Tool naming issues resolved - now uses actual tool names from registry{Style.RESET_ALL}"
        )
        print(f"{Fore.YELLOW}Test duration: up to {config.max_test_duration * 4 / 60:.1f} minutes{Style.RESET_ALL}\n")

        results = await asyncio.wait_for(
            test_suite.run_all_tests(),
            timeout=config.max_test_duration * 4,  # Total timeout for all tests
        )

        # Save results
        results_file = PROJECT_ROOT / "mcp_resilience_test_results.json"
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2, default=str)

        print(f"\n{Fore.CYAN}📁 Detailed results saved to: {results_file}{Style.RESET_ALL}")

        # Exit with appropriate code
        if results["summary"]["resilience_grade"] == "excellent":
            print(f"\n{Fore.GREEN}🚀 MCP system demonstrates excellent resilience!{Style.RESET_ALL}")
            return 0
        elif results["summary"]["resilience_grade"] == "good":
            print(f"\n{Fore.YELLOW}👍 MCP system shows good resilience characteristics.{Style.RESET_ALL}")
            return 0
        else:
            print(f"\n{Fore.RED}⚠️ MCP system resilience needs improvement.{Style.RESET_ALL}")
            return 1

    except TimeoutError:
        print(f"\n{Fore.RED}❌ Resilience tests timed out{Style.RESET_ALL}")
        return 1
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}👋 Resilience tests interrupted by user{Style.RESET_ALL}")
        return 130
    except Exception as e:
        print(f"\n{Fore.RED}❌ Resilience test suite failed: {e}{Style.RESET_ALL}")
        logger.error(f"Test suite failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
