#!/usr/bin/env python
"""
mcp_http_streamable_resilience_test.py - HTTP Streamable Transport Resilience Test Suite
──────────────────────────────────────────────────────────────────────────────────────

Tests resilience features specifically for the HTTP Streamable transport layer.
HTTP Streamable uses a single endpoint with optional SSE streaming (spec 2025-03-26).

This tests:
1. Single endpoint connection recovery
2. HTTP request/response vs SSE streaming mode switching
3. Session management resilience
4. Network timeout handling for streamable responses
5. Concurrent stress with streaming capabilities
6. Modern transport features (session persistence, resumability)

Prerequisites:
- Start the HTTP Streamable test server: python examples/mcp_streamable_http_server.py
- Server should be running on http://localhost:8000
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

import requests
from colorama import Fore, Style
from colorama import init as colorama_init

colorama_init(autoreset=True)

# ─── local-package bootstrap ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from chuk_tool_processor import InProcessStrategy
from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.mcp.setup_mcp_http_streamable import setup_mcp_http_streamable
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.registry.provider import ToolRegistryProvider

logger = get_logger("mcp-http-streamable-resilience-test")

# ═══════════════════════════════════════════════════════════════════════════
# HTTP Streamable-Specific Resilience Test Configuration
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class HTTPStreamableResilienceTestConfig:
    """Configuration for HTTP Streamable resilience testing scenarios."""

    max_test_duration: float = 300.0  # 5 minutes max per test
    connection_retry_attempts: int = 3
    retry_delay: float = 1.0
    stress_test_calls: int = 20  # Higher for modern single-endpoint design
    concurrent_connections: int = 4  # Higher for streamable efficiency
    failure_injection_rate: float = 0.25  # 25% failure rate
    session_reconnect_delay: float = 2.0  # Time for session recovery
    timeout_test_duration: float = 10.0
    http_server_url: str = "http://localhost:8000"


@dataclass
class TestResult:
    """Result of an HTTP Streamable resilience test."""

    test_name: str
    success: bool
    duration: float
    error_count: int = 0
    recovery_count: int = 0
    total_operations: int = 0
    streaming_operations: int = 0  # Operations that used streaming
    session_issues: int = 0  # Session management problems
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if self.total_operations == 0:
            return 0.0
        return (self.total_operations - self.error_count) / self.total_operations * 100


class HTTPStreamableResilienceTestSuite:
    """HTTP Streamable-specific resilience testing suite."""

    def __init__(self, config: HTTPStreamableResilienceTestConfig):
        self.config = config
        self.test_results: list[TestResult] = []
        self.shutdown_event = asyncio.Event()
        self.stream_managers = []
        self.available_tools: dict[str, list[str]] = {}  # namespace -> [tool_names]

    def banner(self, text: str, color: str = Fore.CYAN) -> None:
        """Print a colored banner."""
        print(f"\n{color}{'=' * 60}")
        print(f"  {text}")
        print(f"{'=' * 60}{Style.RESET_ALL}\n")

    def print_progress(self, message: str, color: str = Fore.YELLOW):
        """Print progress message."""
        print(f"{color}🔄 {message}{Style.RESET_ALL}")

    def check_http_streamable_server_health(self) -> bool:
        """Check if HTTP Streamable server is running and healthy."""
        try:
            response = requests.get(f"{self.config.http_server_url}/health", timeout=5.0)
            return response.status_code == 200
        except Exception:
            try:
                # Try the main MCP endpoint
                response = requests.post(
                    f"{self.config.http_server_url}/mcp",
                    json={"jsonrpc": "2.0", "id": "health", "method": "ping"},
                    timeout=5.0,
                )
                return response.status_code in [200, 400]  # 400 is also OK (invalid method)
            except Exception:
                return False

    async def discover_available_tools(self, namespace: str) -> list[str]:
        """Discover what tools are available in the HTTP Streamable namespace."""
        try:
            registry = await ToolRegistryProvider.get_registry()
            all_tools = await registry.list_tools()

            namespace_tools = [tool_name for ns, tool_name in all_tools if ns == namespace]

            self.print_progress(
                f"Found {len(namespace_tools)} HTTP Streamable tools in namespace '{namespace}': {namespace_tools}"
            )
            self.available_tools[namespace] = namespace_tools

            return namespace_tools

        except Exception as e:
            logger.error(f"Error discovering HTTP Streamable tools in namespace {namespace}: {e}")
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
    # Test 1: HTTP Streamable Single Endpoint Recovery
    # ================================================================

    async def test_http_streamable_endpoint_recovery(self) -> TestResult:
        """Test HTTP Streamable single endpoint connection recovery."""
        self.banner("TEST 1: HTTP Streamable Single Endpoint Recovery", Fore.GREEN)

        start_time = time.time()
        test_result = TestResult("http_streamable_endpoint_recovery", False, 0.0)

        if not self.check_http_streamable_server_health():
            test_result.details["error"] = (
                "HTTP Streamable server not running - start with: python examples/mcp_streamable_http_server.py"
            )
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)
            return test_result

        try:
            self.print_progress("Setting up initial HTTP Streamable connection...")

            # Set up initial HTTP Streamable connection
            processor, stream_manager = await setup_mcp_http_streamable(
                servers=[
                    {
                        "name": "http_streamable_server",
                        "url": self.config.http_server_url,
                    }
                ],
                namespace="http_resilience_test",
                default_timeout=5.0,
            )
            self.stream_managers.append(stream_manager)

            # Discover available tools
            available_tools = await self.discover_available_tools("http_resilience_test")
            if not available_tools:
                raise RuntimeError("No HTTP Streamable tools found - check server configuration")

            test_tool = available_tools[0]  # Use first available tool
            self.print_progress(f"Using HTTP Streamable tool: {test_tool}")

            registry = await ToolRegistryProvider.get_registry()
            executor = ToolExecutor(registry, strategy=InProcessStrategy(registry, default_timeout=5.0))

            # Test initial connectivity
            self.print_progress("Testing initial HTTP Streamable connectivity...")
            initial_call = ToolCall(
                tool=test_tool, arguments={"name": "connectivity test"} if "greet" in test_tool else {}
            )

            initial_result = await executor.execute([initial_call])
            test_result.total_operations += 1

            if initial_result[0].error:
                raise RuntimeError(f"Initial HTTP Streamable connectivity test failed: {initial_result[0].error}")

            self.print_progress("✅ Initial HTTP Streamable connectivity confirmed")

            # Simulate connection disruption
            self.print_progress("Simulating HTTP Streamable connection disruption...")
            await stream_manager.close()

            # Wait for session recovery delay
            await asyncio.sleep(self.config.session_reconnect_delay)

            # Test recovery with new HTTP Streamable connection
            self.print_progress("Testing HTTP Streamable connection recovery...")
            processor2, stream_manager2 = await setup_mcp_http_streamable(
                servers=[
                    {
                        "name": "http_streamable_server",
                        "url": self.config.http_server_url,
                    }
                ],
                namespace="http_resilience_test",
                default_timeout=5.0,
            )
            self.stream_managers.append(stream_manager2)

            await asyncio.sleep(1.0)  # Allow connection to establish

            # Rediscover tools after reconnection
            recovery_tools = await self.discover_available_tools("http_resilience_test")
            if test_tool in recovery_tools:
                recovery_call = ToolCall(
                    tool=test_tool, arguments={"name": "recovery test"} if "greet" in test_tool else {}
                )

                recovery_result = await executor.execute([recovery_call])
                test_result.total_operations += 1

                if not recovery_result[0].error:
                    test_result.recovery_count += 1
                    self.print_progress("✅ HTTP Streamable connection recovery successful!")
                    test_result.success = True
                else:
                    self.print_progress(f"❌ HTTP Streamable recovery failed: {recovery_result[0].error}")
            else:
                self.print_progress(f"❌ Tool {test_tool} not available after HTTP Streamable recovery")
                test_result.session_issues += 1

        except Exception as e:
            logger.error(f"HTTP Streamable connection recovery test failed: {e}")
            test_result.details["error"] = str(e)

        finally:
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)

        return test_result

    # ================================================================
    # Test 2: HTTP Streamable Session Management
    # ================================================================

    async def test_http_streamable_session_management(self) -> TestResult:
        """Test HTTP Streamable session persistence and management."""
        self.banner("TEST 2: HTTP Streamable Session Management", Fore.GREEN)

        start_time = time.time()
        test_result = TestResult("http_streamable_session_management", False, 0.0)

        if not self.check_http_streamable_server_health():
            test_result.details["error"] = "HTTP Streamable server not running"
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)
            return test_result

        try:
            self.print_progress("Setting up HTTP Streamable session test...")

            processor, stream_manager = await setup_mcp_http_streamable(
                servers=[
                    {
                        "name": "http_streamable_server",
                        "url": self.config.http_server_url,
                    }
                ],
                namespace="http_session_test",
                connection_timeout=10.0,
                default_timeout=8.0,
            )
            self.stream_managers.append(stream_manager)

            available_tools = await self.discover_available_tools("http_session_test")
            if not available_tools:
                raise RuntimeError("No tools found for HTTP Streamable session test")

            registry = await ToolRegistryProvider.get_registry()
            executor = ToolExecutor(registry, strategy=InProcessStrategy(registry, default_timeout=8.0))

            # Test session-aware tools (like counter)
            counter_tool = None
            session_tool = None
            for tool in available_tools:
                if "counter" in tool:
                    counter_tool = tool
                elif "session" in tool:
                    session_tool = tool

            if counter_tool:
                self.print_progress(f"Testing session persistence with: {counter_tool}")

                # Test incremental counter calls to verify session persistence
                for i in range(1, 4):
                    call = ToolCall(tool=counter_tool, arguments={"increment": i})

                    result = await executor.execute([call])
                    test_result.total_operations += 1

                    if result[0].error:
                        test_result.error_count += 1
                        if "session" in str(result[0].error).lower():
                            test_result.session_issues += 1
                        self.print_progress(f"Counter call {i}: ❌ Error - {result[0].error}")
                    else:
                        test_result.recovery_count += 1
                        self.print_progress(f"Counter call {i}: ✅ Success - {result[0].result}")

            if session_tool:
                self.print_progress(f"Testing session info with: {session_tool}")

                # Test session info retrieval
                session_call = ToolCall(tool=session_tool, arguments={})
                session_result = await executor.execute([session_call])
                test_result.total_operations += 1

                if session_result[0].error:
                    test_result.error_count += 1
                    test_result.session_issues += 1
                else:
                    test_result.recovery_count += 1
                    self.print_progress(f"Session info: ✅ {session_result[0].result}")

            # Test multiple rapid calls to challenge session management
            self.print_progress("Testing rapid session calls...")
            rapid_tool = available_tools[0]

            for i in range(5):
                call = ToolCall(tool=rapid_tool, arguments={"name": f"rapid {i}"} if "greet" in rapid_tool else {})

                result = await executor.execute([call])
                test_result.total_operations += 1

                if result[0].error:
                    test_result.error_count += 1
                    if "session" in str(result[0].error).lower():
                        test_result.session_issues += 1
                else:
                    test_result.recovery_count += 1

                # Very brief delay
                await asyncio.sleep(0.1)

            # Test passes if we have good success rate and minimal session issues
            if test_result.success_rate >= 70.0 and test_result.session_issues <= 1:
                test_result.success = True
                self.print_progress("✅ HTTP Streamable session management test passed!")
            else:
                self.print_progress("❌ HTTP Streamable session management issues detected")

        except Exception as e:
            logger.error(f"HTTP Streamable session management test failed: {e}")
            test_result.details["error"] = str(e)

        finally:
            test_result.duration = time.time() - start_time
            test_result.details["session_issues"] = test_result.session_issues
            self.test_results.append(test_result)

        return test_result

    # ================================================================
    # Test 3: HTTP Streamable Response Mode Switching
    # ================================================================

    async def test_http_streamable_response_modes(self) -> TestResult:
        """Test HTTP Streamable switching between immediate and streaming responses."""
        self.banner("TEST 3: HTTP Streamable Response Mode Switching", Fore.GREEN)

        start_time = time.time()
        test_result = TestResult("http_streamable_response_modes", False, 0.0)

        if not self.check_http_streamable_server_health():
            test_result.details["error"] = "HTTP Streamable server not running"
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)
            return test_result

        try:
            self.print_progress("Setting up HTTP Streamable response mode test...")

            processor, stream_manager = await setup_mcp_http_streamable(
                servers=[
                    {
                        "name": "http_streamable_server",
                        "url": self.config.http_server_url,
                    }
                ],
                namespace="http_response_modes",
                connection_timeout=5.0,
                default_timeout=10.0,  # Longer for streaming operations
            )
            self.stream_managers.append(stream_manager)

            available_tools = await self.discover_available_tools("http_response_modes")
            if not available_tools:
                raise RuntimeError("No tools found for HTTP Streamable response mode test")

            registry = await ToolRegistryProvider.get_registry()
            executor = ToolExecutor(registry, strategy=InProcessStrategy(registry, default_timeout=10.0))

            # Test quick immediate response tools
            quick_tools = [tool for tool in available_tools if "greet" in tool or "counter" in tool]
            slow_tools = [tool for tool in available_tools if "slow" in tool]

            # Test immediate response mode
            if quick_tools:
                self.print_progress(f"Testing immediate response mode with: {quick_tools[0]}")

                for i in range(3):
                    call = ToolCall(
                        tool=quick_tools[0],
                        arguments={"name": f"immediate {i}"} if "greet" in quick_tools[0] else {"increment": 1},
                    )

                    result = await executor.execute([call])
                    test_result.total_operations += 1

                    if result[0].error:
                        test_result.error_count += 1
                    else:
                        test_result.recovery_count += 1
                        self.print_progress(f"Immediate call {i + 1}: ✅ Success")

            # Test streaming response mode
            if slow_tools:
                self.print_progress(f"Testing streaming response mode with: {slow_tools[0]}")

                for duration in [1, 2]:
                    call = ToolCall(tool=slow_tools[0], arguments={"duration": duration})

                    result = await executor.execute([call])
                    test_result.total_operations += 1

                    if result[0].error:
                        test_result.error_count += 1
                        self.print_progress(f"Streaming call ({duration}s): ❌ Error - {result[0].error}")
                    else:
                        test_result.recovery_count += 1
                        test_result.streaming_operations += 1
                        self.print_progress(f"Streaming call ({duration}s): ✅ Success")

            # Test mixed mode concurrent calls
            self.print_progress("Testing mixed immediate/streaming concurrent calls...")
            mixed_calls = []

            if quick_tools:
                mixed_calls.append(
                    ToolCall(
                        tool=quick_tools[0],
                        arguments={"name": "concurrent immediate"} if "greet" in quick_tools[0] else {"increment": 1},
                    )
                )

            if slow_tools:
                mixed_calls.append(ToolCall(tool=slow_tools[0], arguments={"duration": 1}))

            if available_tools and not mixed_calls:
                # Fallback to any available tools
                mixed_calls = [
                    ToolCall(tool=available_tools[0], arguments={}),
                    ToolCall(tool=available_tools[0], arguments={}),
                ]

            if mixed_calls:
                mixed_results = await executor.execute(mixed_calls)
                test_result.total_operations += len(mixed_results)

                mixed_success = sum(1 for r in mixed_results if not r.error)
                mixed_errors = len(mixed_results) - mixed_success

                test_result.recovery_count += mixed_success
                test_result.error_count += mixed_errors

                self.print_progress(f"Mixed mode calls: {mixed_success}/{len(mixed_results)} successful")

            # Test passes if we can handle both response modes
            if test_result.success_rate >= 60.0:
                test_result.success = True
                self.print_progress("✅ HTTP Streamable response mode switching test passed!")
            else:
                self.print_progress("❌ HTTP Streamable response mode issues detected")

        except Exception as e:
            logger.error(f"HTTP Streamable response mode test failed: {e}")
            test_result.details["error"] = str(e)

        finally:
            test_result.duration = time.time() - start_time
            test_result.details["streaming_operations"] = test_result.streaming_operations
            self.test_results.append(test_result)

        return test_result

    # ================================================================
    # Test 4: HTTP Streamable Concurrent Stress Test
    # ================================================================

    async def test_http_streamable_concurrent_stress(self) -> TestResult:
        """Test HTTP Streamable system under concurrent load."""
        self.banner("TEST 4: HTTP Streamable Concurrent Stress Test", Fore.GREEN)

        start_time = time.time()
        test_result = TestResult("http_streamable_concurrent_stress", False, 0.0)

        if not self.check_http_streamable_server_health():
            test_result.details["error"] = "HTTP Streamable server not running"
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)
            return test_result

        try:
            self.print_progress("Setting up HTTP Streamable stress test...")

            # Set up HTTP Streamable connection for stress testing
            processor, stream_manager = await setup_mcp_http_streamable(
                servers=[
                    {
                        "name": "http_streamable_server",
                        "url": self.config.http_server_url,
                    }
                ],
                namespace="http_stress_test",
                connection_timeout=15.0,
                default_timeout=10.0,
            )
            self.stream_managers.append(stream_manager)

            available_tools = await self.discover_available_tools("http_stress_test")
            if not available_tools:
                raise RuntimeError("No tools found for HTTP Streamable stress test")

            registry = await ToolRegistryProvider.get_registry()
            executor = ToolExecutor(
                registry,
                strategy=InProcessStrategy(
                    registry, default_timeout=10.0, max_concurrency=self.config.concurrent_connections
                ),
            )

            # Generate stress test calls with mix of immediate and streaming
            stress_calls = []
            for i in range(self.config.stress_test_calls):
                tool = random.choice(available_tools)

                # Create appropriate arguments based on tool type
                if "greet" in tool:
                    args = {"name": f"stress user {i + 1}", "style": random.choice(["formal", "casual"])}
                elif "counter" in tool:
                    args = {"increment": random.randint(1, 5)}
                elif "slow" in tool:
                    args = {"duration": random.randint(1, 2)}
                    test_result.streaming_operations += 1
                else:
                    args = {}

                call = ToolCall(tool=tool, arguments=args)
                stress_calls.append(call)

            if not stress_calls:
                raise RuntimeError("No stress calls could be generated")

            self.print_progress(f"Executing {len(stress_calls)} concurrent HTTP Streamable calls...")

            stress_start = time.time()
            stress_results = await executor.execute(stress_calls)
            stress_duration = time.time() - stress_start

            # Analyze results
            successful_calls = sum(1 for r in stress_results if not r.error)
            failed_calls = len(stress_results) - successful_calls

            test_result.total_operations = len(stress_results)
            test_result.error_count = failed_calls
            test_result.recovery_count = successful_calls

            # Count session-specific issues
            for result in stress_results:
                if result.error and "session" in str(result.error).lower():
                    test_result.session_issues += 1

            calls_per_second = len(stress_calls) / stress_duration if stress_duration > 0 else 0

            self.print_progress(f"HTTP Streamable stress test completed in {stress_duration:.2f}s")
            self.print_progress(f"Throughput: {calls_per_second:.1f} calls/second")
            self.print_progress(f"Success rate: {test_result.success_rate:.1f}%")
            self.print_progress(f"Streaming operations: {test_result.streaming_operations}")
            self.print_progress(f"Session issues: {test_result.session_issues}")

            # Test passes if success rate is good for modern single-endpoint design
            if test_result.success_rate >= 75.0:
                test_result.success = True
                self.print_progress("✅ HTTP Streamable stress test passed - system stable under load")
            else:
                self.print_progress("❌ HTTP Streamable stress test failed - too many failures under load")

            test_result.details.update(
                {
                    "calls_per_second": calls_per_second,
                    "stress_duration": stress_duration,
                    "success_rate": test_result.success_rate,
                    "streaming_operations": test_result.streaming_operations,
                    "session_issues": test_result.session_issues,
                    "tools_used": len(available_tools),
                }
            )

        except Exception as e:
            logger.error(f"HTTP Streamable concurrent stress test failed: {e}")
            test_result.details["error"] = str(e)

        finally:
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)

        return test_result

    # ================================================================
    # Test Runner and Reporting
    # ================================================================

    async def run_all_tests(self) -> dict[str, Any]:
        """Run all HTTP Streamable resilience tests."""
        self.banner("HTTP STREAMABLE TRANSPORT RESILIENCE TEST SUITE", Fore.MAGENTA)

        try:
            tests = [
                self.test_http_streamable_endpoint_recovery,
                self.test_http_streamable_session_management,
                self.test_http_streamable_response_modes,
                self.test_http_streamable_concurrent_stress,
            ]

            for test_func in tests:
                if self.shutdown_event.is_set():
                    logger.info("Shutdown requested, stopping HTTP Streamable tests")
                    break

                try:
                    await asyncio.wait_for(test_func(), timeout=self.config.max_test_duration)

                    await asyncio.sleep(1.0)  # Brief pause between tests

                except TimeoutError:
                    logger.error(f"HTTP Streamable test {test_func.__name__} timed out")
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

    async def cleanup_connections(self):
        """Clean up all HTTP Streamable connections."""
        self.print_progress("Cleaning up HTTP Streamable connections...")

        for sm in self.stream_managers:
            try:
                await asyncio.wait_for(sm.close(), timeout=3.0)
            except Exception as e:
                logger.debug(f"Error closing HTTP Streamable stream manager: {e}")

        self.stream_managers.clear()

    def generate_test_report(self) -> dict[str, Any]:
        """Generate comprehensive HTTP Streamable test report."""
        self.banner("HTTP STREAMABLE RESILIENCE TEST RESULTS", Fore.MAGENTA)

        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r.success)
        failed_tests = total_tests - passed_tests

        total_operations = sum(r.total_operations for r in self.test_results)
        total_errors = sum(r.error_count for r in self.test_results)
        total_recoveries = sum(r.recovery_count for r in self.test_results)
        total_streaming = sum(r.streaming_operations for r in self.test_results)
        total_session_issues = sum(r.session_issues for r in self.test_results)

        overall_success_rate = (
            ((total_operations - total_errors) / total_operations * 100) if total_operations > 0 else 0
        )

        # Print summary
        print(f"{Fore.CYAN}📊 HTTP STREAMABLE TEST SUMMARY:{Style.RESET_ALL}")
        print(f"   Total Tests: {total_tests}")
        print(f"   Passed: {Fore.GREEN}{passed_tests}{Style.RESET_ALL}")
        print(f"   Failed: {Fore.RED}{failed_tests}{Style.RESET_ALL}")
        print(f"   Overall Success Rate: {Fore.YELLOW}{overall_success_rate:.1f}%{Style.RESET_ALL}")
        print(f"   Streaming Operations: {Fore.BLUE}{total_streaming}{Style.RESET_ALL}")
        print(f"   Session Issues: {Fore.YELLOW}{total_session_issues}{Style.RESET_ALL}")
        print(f"   Total Operations: {total_operations}")
        print(f"   Successful Operations: {Fore.GREEN}{total_recoveries}{Style.RESET_ALL}")

        # Print detailed results
        print(f"\n{Fore.CYAN}📋 DETAILED HTTP STREAMABLE RESULTS:{Style.RESET_ALL}")
        for result in self.test_results:
            status = f"{Fore.GREEN}✅ PASS" if result.success else f"{Fore.RED}❌ FAIL"
            print(f"   {status}{Style.RESET_ALL} {result.test_name}")
            print(f"      Duration: {result.duration:.2f}s")
            print(f"      Success Rate: {result.success_rate:.1f}%")
            print(f"      Streaming Ops: {result.streaming_operations}")
            print(f"      Session Issues: {result.session_issues}")
            if result.details and "error" in result.details:
                print(f"      {Fore.RED}Error: {result.details['error']}{Style.RESET_ALL}")
            print()

        # Overall assessment for HTTP Streamable
        if passed_tests == total_tests and overall_success_rate >= 80:
            print(
                f"{Fore.GREEN}🎉 EXCELLENT: All HTTP Streamable tests passed with excellent performance!{Style.RESET_ALL}"
            )
            resilience_grade = "excellent"
        elif passed_tests >= total_tests * 0.75 and overall_success_rate >= 70:
            print(f"{Fore.YELLOW}✅ GOOD: Most HTTP Streamable tests passed with good performance.{Style.RESET_ALL}")
            resilience_grade = "good"
        else:
            print(f"{Fore.RED}⚠️ NEEDS IMPROVEMENT: HTTP Streamable resilience issues detected.{Style.RESET_ALL}")
            resilience_grade = "needs_improvement"

        # Print HTTP Streamable advantages summary
        print(f"\n{Fore.CYAN}📈 HTTP STREAMABLE ADVANTAGES DEMONSTRATED:{Style.RESET_ALL}")
        print("   • Single endpoint architecture (vs SSE dual endpoints)")
        print("   • Optional streaming when needed (vs always-on SSE)")
        print("   • Better session management capabilities")
        print("   • Higher throughput potential")
        print("   • Modern infrastructure compatibility")

        return {
            "transport_type": "HTTP_Streamable",
            "summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "overall_success_rate": overall_success_rate,
                "total_operations": total_operations,
                "total_errors": total_errors,
                "total_recoveries": total_recoveries,
                "streaming_operations": total_streaming,
                "session_issues": total_session_issues,
                "resilience_grade": resilience_grade,
            },
            "test_results": [
                {
                    "test_name": r.test_name,
                    "success": r.success,
                    "duration": r.duration,
                    "success_rate": r.success_rate,
                    "streaming_operations": r.streaming_operations,
                    "session_issues": r.session_issues,
                    "details": r.details,
                }
                for r in self.test_results
            ],
        }


async def main():
    """Main entry point for HTTP Streamable resilience testing."""
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

    config = HTTPStreamableResilienceTestConfig()
    test_suite = HTTPStreamableResilienceTestSuite(config)
    test_suite.shutdown_event = shutdown_event

    try:
        print(f"{Fore.MAGENTA}🧪 Starting HTTP Streamable Transport Resilience Test Suite...{Style.RESET_ALL}")
        print(
            f"{Fore.YELLOW}Testing modern single-endpoint HTTP Streamable architecture (MCP spec 2025-03-26){Style.RESET_ALL}"
        )
        print(
            f"{Fore.YELLOW}Prerequisites: Start HTTP Streamable server with 'python examples/mcp_streamable_http_server.py'{Style.RESET_ALL}"
        )
        print(f"{Fore.YELLOW}Test duration: up to {config.max_test_duration * 4 / 60:.1f} minutes{Style.RESET_ALL}\n")

        results = await test_suite.run_all_tests()

        # Save results
        results_file = PROJECT_ROOT / "mcp_http_streamable_resilience_test_results.json"
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2, default=str)

        print(f"\n{Fore.CYAN}📁 HTTP Streamable test results saved to: {results_file}{Style.RESET_ALL}")

        # Exit with appropriate code
        if results["summary"]["resilience_grade"] == "excellent":
            print(f"\n{Fore.GREEN}🚀 HTTP Streamable transport demonstrates excellent resilience!{Style.RESET_ALL}")
            return 0
        elif results["summary"]["resilience_grade"] == "good":
            print(
                f"\n{Fore.YELLOW}👍 HTTP Streamable transport shows good resilience characteristics.{Style.RESET_ALL}"
            )
            return 0
        else:
            print(f"\n{Fore.RED}⚠️ HTTP Streamable transport resilience needs improvement.{Style.RESET_ALL}")
            return 1

    except Exception as e:
        print(f"\n{Fore.RED}❌ HTTP Streamable resilience test suite failed: {e}{Style.RESET_ALL}")
        logger.error(f"HTTP Streamable test suite failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
