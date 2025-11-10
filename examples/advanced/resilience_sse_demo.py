#!/usr/bin/env python
"""
resilience_sse_demo.py - SSE Transport Resilience Test Suite
──────────────────────────────────────────────────────────────

Tests resilience features specifically for the SSE transport layer.
SSE transport uses dual endpoints (one for SSE connection, one for HTTP POST messages).

This tests:
1. SSE connection recovery
2. HTTP message endpoint failures
3. Dual endpoint coordination issues
4. Network timeout handling for SSE streams
5. Concurrent stress with SSE connections

Prerequisites:
- Start the SSE test server: python examples/test_sse_server.py
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
from chuk_tool_processor.mcp.setup_mcp_sse import setup_mcp_sse
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.registry.provider import ToolRegistryProvider

logger = get_logger("mcp-sse-resilience-test")

# ═══════════════════════════════════════════════════════════════════════════
# SSE-Specific Resilience Test Configuration
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class SSEResilienceTestConfig:
    """Configuration for SSE resilience testing scenarios."""

    max_test_duration: float = 300.0  # 5 minutes max per test
    connection_retry_attempts: int = 3
    retry_delay: float = 1.0
    stress_test_calls: int = 15  # Moderate for SSE stability
    concurrent_connections: int = 2  # Lower for SSE dual-endpoint complexity
    failure_injection_rate: float = 0.2  # 20% failure rate for SSE
    sse_reconnect_delay: float = 3.0  # Time for SSE reconnection
    timeout_test_duration: float = 8.0
    sse_server_url: str = "http://localhost:8000"


@dataclass
class TestResult:
    """Result of an SSE resilience test."""

    test_name: str
    success: bool
    duration: float
    error_count: int = 0
    recovery_count: int = 0
    total_operations: int = 0
    sse_specific_issues: int = 0  # SSE-specific problems
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if self.total_operations == 0:
            return 0.0
        return (self.total_operations - self.error_count) / self.total_operations * 100


class SSEResilienceTestSuite:
    """SSE-specific resilience testing suite."""

    def __init__(self, config: SSEResilienceTestConfig):
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

    def check_sse_server_health(self) -> bool:
        """Check if SSE server is running and healthy."""
        try:
            response = requests.get(f"{self.config.sse_server_url}/health", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False

    async def discover_available_tools(self, namespace: str) -> list[str]:
        """Discover what tools are available in the SSE namespace."""
        try:
            registry = await ToolRegistryProvider.get_registry()
            all_tools = await registry.list_tools()

            namespace_tools = [tool_name for ns, tool_name in all_tools if ns == namespace]

            self.print_progress(f"Found {len(namespace_tools)} SSE tools in namespace '{namespace}': {namespace_tools}")
            self.available_tools[namespace] = namespace_tools

            return namespace_tools

        except Exception as e:
            logger.error(f"Error discovering SSE tools in namespace {namespace}: {e}")
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
    # Test 1: SSE Connection Recovery
    # ================================================================

    async def test_sse_connection_recovery(self) -> TestResult:
        """Test SSE connection loss and recovery."""
        self.banner("TEST 1: SSE Connection Recovery", Fore.GREEN)

        start_time = time.time()
        test_result = TestResult("sse_connection_recovery", False, 0.0)

        if not self.check_sse_server_health():
            test_result.details["error"] = "SSE server not running - start with: python examples/test_sse_server.py"
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)
            return test_result

        try:
            self.print_progress("Setting up initial SSE connection...")

            # Set up initial SSE connection
            processor, stream_manager = await setup_mcp_sse(
                servers=[
                    {
                        "name": "mock_perplexity_server",
                        "url": self.config.sse_server_url,
                    }
                ],
                namespace="sse_resilience_test",
                default_timeout=5.0,
            )
            self.stream_managers.append(stream_manager)

            # Discover available tools
            available_tools = await self.discover_available_tools("sse_resilience_test")
            if not available_tools:
                raise RuntimeError("No SSE tools found - check server configuration")

            test_tool = available_tools[0]  # Use first available tool
            self.print_progress(f"Using SSE tool: {test_tool}")

            registry = await ToolRegistryProvider.get_registry()
            executor = ToolExecutor(registry, strategy=InProcessStrategy(registry, default_timeout=5.0))

            # Test initial connectivity
            self.print_progress("Testing initial SSE connectivity...")
            initial_call = ToolCall(
                tool=test_tool, arguments={"query": "test connectivity"} if "search" in test_tool else {}
            )

            initial_result = await executor.execute([initial_call])
            test_result.total_operations += 1

            if initial_result[0].error:
                raise RuntimeError(f"Initial SSE connectivity test failed: {initial_result[0].error}")

            self.print_progress("✅ Initial SSE connectivity confirmed")

            # Simulate SSE connection disruption
            self.print_progress("Simulating SSE connection disruption...")
            await stream_manager.close()

            # Wait for SSE reconnection delay
            await asyncio.sleep(self.config.sse_reconnect_delay)

            # Test recovery with new SSE connection
            self.print_progress("Testing SSE connection recovery...")
            processor2, stream_manager2 = await setup_mcp_sse(
                servers=[
                    {
                        "name": "mock_perplexity_server",
                        "url": self.config.sse_server_url,
                    }
                ],
                namespace="sse_resilience_test",
                default_timeout=5.0,
            )
            self.stream_managers.append(stream_manager2)

            await asyncio.sleep(2.0)  # Allow SSE to establish

            # Rediscover tools after SSE reconnection
            recovery_tools = await self.discover_available_tools("sse_resilience_test")
            if test_tool in recovery_tools:
                recovery_call = ToolCall(
                    tool=test_tool, arguments={"query": "test recovery"} if "search" in test_tool else {}
                )

                recovery_result = await executor.execute([recovery_call])
                test_result.total_operations += 1

                if not recovery_result[0].error:
                    test_result.recovery_count += 1
                    self.print_progress("✅ SSE connection recovery successful!")
                    test_result.success = True
                else:
                    self.print_progress(f"❌ SSE recovery failed: {recovery_result[0].error}")
                    test_result.sse_specific_issues += 1
            else:
                self.print_progress(f"❌ Tool {test_tool} not available after SSE recovery")
                test_result.sse_specific_issues += 1

        except Exception as e:
            logger.error(f"SSE connection recovery test failed: {e}")
            test_result.details["error"] = str(e)

        finally:
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)

        return test_result

    # ================================================================
    # Test 2: SSE Dual Endpoint Coordination
    # ================================================================

    async def test_sse_dual_endpoint_coordination(self) -> TestResult:
        """Test SSE's dual endpoint (SSE stream + HTTP POST) coordination."""
        self.banner("TEST 2: SSE Dual Endpoint Coordination", Fore.GREEN)

        start_time = time.time()
        test_result = TestResult("sse_dual_endpoint_coordination", False, 0.0)

        if not self.check_sse_server_health():
            test_result.details["error"] = "SSE server not running"
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)
            return test_result

        try:
            self.print_progress("Setting up SSE dual endpoint test...")

            processor, stream_manager = await setup_mcp_sse(
                servers=[
                    {
                        "name": "mock_perplexity_server",
                        "url": self.config.sse_server_url,
                    }
                ],
                namespace="sse_dual_endpoint",
                connection_timeout=10.0,
                default_timeout=8.0,
            )
            self.stream_managers.append(stream_manager)

            available_tools = await self.discover_available_tools("sse_dual_endpoint")
            if not available_tools:
                raise RuntimeError("No tools found for SSE dual endpoint test")

            test_tool = available_tools[0]
            self.print_progress(f"Using tool for dual endpoint test: {test_tool}")

            registry = await ToolRegistryProvider.get_registry()
            executor = ToolExecutor(registry, strategy=InProcessStrategy(registry, default_timeout=8.0))

            # Test rapid sequential calls to stress dual endpoint coordination
            self.print_progress("Testing rapid sequential SSE calls...")
            for i in range(5):
                call = ToolCall(
                    tool=test_tool, arguments={"query": f"rapid test {i + 1}"} if "search" in test_tool else {}
                )

                result = await executor.execute([call])
                test_result.total_operations += 1

                if result[0].error:
                    test_result.error_count += 1
                    if "endpoint" in str(result[0].error).lower():
                        test_result.sse_specific_issues += 1
                    self.print_progress(f"Call {i + 1}: ❌ Error - {result[0].error}")
                else:
                    test_result.recovery_count += 1
                    self.print_progress(f"Call {i + 1}: ✅ Success")

                # Small delay between calls
                await asyncio.sleep(0.5)

            # Test concurrent calls to challenge endpoint coordination
            self.print_progress("Testing concurrent SSE calls...")
            concurrent_calls = [
                ToolCall(tool=test_tool, arguments={"query": f"concurrent test {i}"} if "search" in test_tool else {})
                for i in range(3)
            ]

            concurrent_results = await executor.execute(concurrent_calls)
            test_result.total_operations += len(concurrent_results)

            concurrent_success = sum(1 for r in concurrent_results if not r.error)
            concurrent_errors = len(concurrent_results) - concurrent_success

            test_result.recovery_count += concurrent_success
            test_result.error_count += concurrent_errors

            # Check for SSE-specific issues in concurrent results
            for result in concurrent_results:
                if result.error and "endpoint" in str(result.error).lower():
                    test_result.sse_specific_issues += 1

            self.print_progress(f"Concurrent calls: {concurrent_success}/{len(concurrent_results)} successful")

            # Test passes if we have reasonable success rate and handled SSE complexity
            if test_result.success_rate >= 60.0:
                test_result.success = True
                self.print_progress("✅ SSE dual endpoint coordination test passed!")
            else:
                self.print_progress("❌ SSE dual endpoint coordination issues detected")

        except Exception as e:
            logger.error(f"SSE dual endpoint coordination test failed: {e}")
            test_result.details["error"] = str(e)

        finally:
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)

        return test_result

    # ================================================================
    # Test 3: SSE Stream Timeout Recovery
    # ================================================================

    async def test_sse_stream_timeout_recovery(self) -> TestResult:
        """Test recovery from SSE stream timeouts."""
        self.banner("TEST 3: SSE Stream Timeout Recovery", Fore.GREEN)

        start_time = time.time()
        test_result = TestResult("sse_stream_timeout_recovery", False, 0.0)

        if not self.check_sse_server_health():
            test_result.details["error"] = "SSE server not running"
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)
            return test_result

        try:
            self.print_progress("Setting up SSE stream timeout test...")

            processor, stream_manager = await setup_mcp_sse(
                servers=[
                    {
                        "name": "mock_perplexity_server",
                        "url": self.config.sse_server_url,
                    }
                ],
                namespace="sse_timeout_test",
                connection_timeout=5.0,
                default_timeout=2.0,  # Short timeout for testing
            )
            self.stream_managers.append(stream_manager)

            available_tools = await self.discover_available_tools("sse_timeout_test")
            if not available_tools:
                raise RuntimeError("No tools found for SSE timeout test")

            test_tool = available_tools[0]
            self.print_progress(f"Using tool for timeout test: {test_tool}")

            registry = await ToolRegistryProvider.get_registry()

            # Test with aggressive timeouts
            timeout_executor = ToolExecutor(
                registry,
                strategy=InProcessStrategy(registry, default_timeout=1.0),  # Very short
            )

            self.print_progress("Testing with aggressive SSE timeouts...")
            for i in range(3):
                try:
                    call = ToolCall(
                        tool=test_tool, arguments={"query": "timeout test"} if "search" in test_tool else {}
                    )

                    result = await asyncio.wait_for(
                        timeout_executor.execute([call]),
                        timeout=1.5,  # Even shorter external timeout
                    )
                    test_result.total_operations += 1

                    if result[0].error:
                        test_result.error_count += 1
                        if "timeout" in str(result[0].error).lower():
                            self.print_progress(f"Timeout call {i + 1}: ⏱️ Timeout (expected)")
                        else:
                            self.print_progress(f"Timeout call {i + 1}: ❌ Error - {result[0].error}")
                    else:
                        test_result.recovery_count += 1
                        self.print_progress(f"Timeout call {i + 1}: ✅ Success (unexpected)")

                except TimeoutError:
                    test_result.total_operations += 1
                    test_result.error_count += 1
                    self.print_progress(f"Timeout call {i + 1}: ⏱️ External timeout (expected)")

            # Test recovery with reasonable timeouts
            self.print_progress("Testing SSE timeout recovery...")
            recovery_executor = ToolExecutor(registry, strategy=InProcessStrategy(registry, default_timeout=10.0))

            for i in range(3):
                recovery_call = ToolCall(
                    tool=test_tool, arguments={"query": f"recovery test {i + 1}"} if "search" in test_tool else {}
                )

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
                    f"✅ SSE timeout recovery successful! {test_result.recovery_count} recovery calls succeeded"
                )
            else:
                self.print_progress("❌ No successful SSE recovery calls")

        except Exception as e:
            logger.error(f"SSE stream timeout recovery test failed: {e}")
            test_result.details["error"] = str(e)

        finally:
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)

        return test_result

    # ================================================================
    # Test 4: SSE Concurrent Stress Test
    # ================================================================

    async def test_sse_concurrent_stress(self) -> TestResult:
        """Test SSE system under concurrent load."""
        self.banner("TEST 4: SSE Concurrent Stress Test", Fore.GREEN)

        start_time = time.time()
        test_result = TestResult("sse_concurrent_stress", False, 0.0)

        if not self.check_sse_server_health():
            test_result.details["error"] = "SSE server not running"
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)
            return test_result

        try:
            self.print_progress("Setting up SSE stress test...")

            # Set up SSE connection for stress testing
            processor, stream_manager = await setup_mcp_sse(
                servers=[
                    {
                        "name": "mock_perplexity_server",
                        "url": self.config.sse_server_url,
                    }
                ],
                namespace="sse_stress_test",
                connection_timeout=15.0,
                default_timeout=10.0,
            )
            self.stream_managers.append(stream_manager)

            available_tools = await self.discover_available_tools("sse_stress_test")
            if not available_tools:
                raise RuntimeError("No tools found for SSE stress test")

            registry = await ToolRegistryProvider.get_registry()
            executor = ToolExecutor(
                registry,
                strategy=InProcessStrategy(
                    registry,
                    default_timeout=10.0,
                    max_concurrency=self.config.concurrent_connections,  # Limited for SSE
                ),
            )

            # Generate stress test calls
            stress_calls = []
            for i in range(self.config.stress_test_calls):
                tool = random.choice(available_tools)

                # Create appropriate arguments
                if "search" in tool:
                    args = {"query": f"stress test query {i + 1}"}
                elif "fact" in tool:
                    args = {"query": f"fact test {i + 1}"}
                else:
                    args = {"query": f"test {i + 1}"}

                call = ToolCall(tool=tool, arguments=args)
                stress_calls.append(call)

            if not stress_calls:
                raise RuntimeError("No stress calls could be generated")

            self.print_progress(f"Executing {len(stress_calls)} concurrent SSE calls...")

            stress_start = time.time()
            stress_results = await executor.execute(stress_calls)
            stress_duration = time.time() - stress_start

            # Analyze results
            successful_calls = sum(1 for r in stress_results if not r.error)
            failed_calls = len(stress_results) - successful_calls

            test_result.total_operations = len(stress_results)
            test_result.error_count = failed_calls
            test_result.recovery_count = successful_calls

            # Count SSE-specific issues
            for result in stress_results:
                if result.error and any(
                    keyword in str(result.error).lower() for keyword in ["endpoint", "sse", "stream"]
                ):
                    test_result.sse_specific_issues += 1

            calls_per_second = len(stress_calls) / stress_duration if stress_duration > 0 else 0

            self.print_progress(f"SSE stress test completed in {stress_duration:.2f}s")
            self.print_progress(f"Throughput: {calls_per_second:.1f} calls/second")
            self.print_progress(f"Success rate: {test_result.success_rate:.1f}%")
            self.print_progress(f"SSE-specific issues: {test_result.sse_specific_issues}")

            # Test passes if success rate is reasonable for SSE complexity
            if test_result.success_rate >= 50.0:  # Lower threshold for SSE dual-endpoint complexity
                test_result.success = True
                self.print_progress("✅ SSE stress test passed - system stable under load")
            else:
                self.print_progress("❌ SSE stress test failed - too many failures under load")

            test_result.details.update(
                {
                    "calls_per_second": calls_per_second,
                    "stress_duration": stress_duration,
                    "success_rate": test_result.success_rate,
                    "sse_specific_issues": test_result.sse_specific_issues,
                    "tools_used": len(available_tools),
                }
            )

        except Exception as e:
            logger.error(f"SSE concurrent stress test failed: {e}")
            test_result.details["error"] = str(e)

        finally:
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)

        return test_result

    # ================================================================
    # Test Runner and Reporting
    # ================================================================

    async def run_all_tests(self) -> dict[str, Any]:
        """Run all SSE resilience tests."""
        self.banner("SSE TRANSPORT RESILIENCE TEST SUITE", Fore.MAGENTA)

        try:
            tests = [
                self.test_sse_connection_recovery,
                self.test_sse_dual_endpoint_coordination,
                self.test_sse_stream_timeout_recovery,
                self.test_sse_concurrent_stress,
            ]

            for test_func in tests:
                if self.shutdown_event.is_set():
                    logger.info("Shutdown requested, stopping SSE tests")
                    break

                try:
                    await asyncio.wait_for(test_func(), timeout=self.config.max_test_duration)

                    await asyncio.sleep(1.0)  # Brief pause between tests

                except TimeoutError:
                    logger.error(f"SSE test {test_func.__name__} timed out")
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
        """Clean up all SSE connections."""
        self.print_progress("Cleaning up SSE connections...")

        for sm in self.stream_managers:
            try:
                await asyncio.wait_for(sm.close(), timeout=3.0)
            except Exception as e:
                logger.debug(f"Error closing SSE stream manager: {e}")

        self.stream_managers.clear()

    def generate_test_report(self) -> dict[str, Any]:
        """Generate comprehensive SSE test report."""
        self.banner("SSE RESILIENCE TEST RESULTS", Fore.MAGENTA)

        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r.success)
        failed_tests = total_tests - passed_tests

        total_operations = sum(r.total_operations for r in self.test_results)
        total_errors = sum(r.error_count for r in self.test_results)
        total_recoveries = sum(r.recovery_count for r in self.test_results)
        total_sse_issues = sum(r.sse_specific_issues for r in self.test_results)

        overall_success_rate = (
            ((total_operations - total_errors) / total_operations * 100) if total_operations > 0 else 0
        )

        # Print summary
        print(f"{Fore.CYAN}📊 SSE TEST SUMMARY:{Style.RESET_ALL}")
        print(f"   Total Tests: {total_tests}")
        print(f"   Passed: {Fore.GREEN}{passed_tests}{Style.RESET_ALL}")
        print(f"   Failed: {Fore.RED}{failed_tests}{Style.RESET_ALL}")
        print(f"   Overall Success Rate: {Fore.YELLOW}{overall_success_rate:.1f}%{Style.RESET_ALL}")
        print(f"   SSE-Specific Issues: {Fore.YELLOW}{total_sse_issues}{Style.RESET_ALL}")
        print(f"   Total Operations: {total_operations}")
        print(f"   Successful Operations: {Fore.GREEN}{total_recoveries}{Style.RESET_ALL}")

        # Print detailed results
        print(f"\n{Fore.CYAN}📋 DETAILED SSE RESULTS:{Style.RESET_ALL}")
        for result in self.test_results:
            status = f"{Fore.GREEN}✅ PASS" if result.success else f"{Fore.RED}❌ FAIL"
            print(f"   {status}{Style.RESET_ALL} {result.test_name}")
            print(f"      Duration: {result.duration:.2f}s")
            print(f"      Success Rate: {result.success_rate:.1f}%")
            print(f"      SSE Issues: {result.sse_specific_issues}")
            if result.details and "error" in result.details:
                print(f"      {Fore.RED}Error: {result.details['error']}{Style.RESET_ALL}")
            print()

        # Overall assessment for SSE
        if passed_tests == total_tests and overall_success_rate >= 70:
            print(f"{Fore.GREEN}🎉 EXCELLENT: All SSE tests passed with good resilience!{Style.RESET_ALL}")
            resilience_grade = "excellent"
        elif passed_tests >= total_tests * 0.75 and overall_success_rate >= 50:
            print(f"{Fore.YELLOW}✅ GOOD: Most SSE tests passed considering dual-endpoint complexity.{Style.RESET_ALL}")
            resilience_grade = "good"
        else:
            print(f"{Fore.RED}⚠️ NEEDS IMPROVEMENT: SSE resilience issues detected.{Style.RESET_ALL}")
            resilience_grade = "needs_improvement"

        return {
            "transport_type": "SSE",
            "summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "overall_success_rate": overall_success_rate,
                "total_operations": total_operations,
                "total_errors": total_errors,
                "total_recoveries": total_recoveries,
                "sse_specific_issues": total_sse_issues,
                "resilience_grade": resilience_grade,
            },
            "test_results": [
                {
                    "test_name": r.test_name,
                    "success": r.success,
                    "duration": r.duration,
                    "success_rate": r.success_rate,
                    "sse_specific_issues": r.sse_specific_issues,
                    "details": r.details,
                }
                for r in self.test_results
            ],
        }


async def main():
    """Main entry point for SSE resilience testing."""
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

    config = SSEResilienceTestConfig()
    test_suite = SSEResilienceTestSuite(config)
    test_suite.shutdown_event = shutdown_event

    try:
        print(f"{Fore.MAGENTA}🧪 Starting SSE Transport Resilience Test Suite...{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Testing SSE dual-endpoint architecture resilience{Style.RESET_ALL}")
        print(
            f"{Fore.YELLOW}Prerequisites: Start SSE server with 'python examples/test_sse_server.py'{Style.RESET_ALL}"
        )
        print(f"{Fore.YELLOW}Test duration: up to {config.max_test_duration * 4 / 60:.1f} minutes{Style.RESET_ALL}\n")

        results = await test_suite.run_all_tests()

        # Save results
        results_file = PROJECT_ROOT / "mcp_sse_resilience_test_results.json"
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2, default=str)

        print(f"\n{Fore.CYAN}📁 SSE test results saved to: {results_file}{Style.RESET_ALL}")

        # Exit with appropriate code
        if results["summary"]["resilience_grade"] == "excellent":
            print(f"\n{Fore.GREEN}🚀 SSE transport demonstrates excellent resilience!{Style.RESET_ALL}")
            return 0
        elif results["summary"]["resilience_grade"] == "good":
            print(f"\n{Fore.YELLOW}👍 SSE transport shows good resilience characteristics.{Style.RESET_ALL}")
            return 0
        else:
            print(f"\n{Fore.RED}⚠️ SSE transport resilience needs improvement.{Style.RESET_ALL}")
            return 1

    except Exception as e:
        print(f"\n{Fore.RED}❌ SSE resilience test suite failed: {e}{Style.RESET_ALL}")
        logger.error(f"SSE test suite failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
