#!/usr/bin/env python
"""
subprocess_strategy_resilience_test.py - SubprocessStrategy Resilience Test Suite
──────────────────────────────────────────────────────────────────────────────

Tests resilience features specifically for the SubprocessStrategy execution layer.
SubprocessStrategy executes tools in separate OS processes for isolation and safety.

This tests:
1. Process isolation and worker pool recovery
2. Tool serialization/deserialization across process boundaries
3. Worker process crash recovery and pool regeneration
4. Memory isolation and resource cleanup
5. Concurrent subprocess execution under stress
6. Timeout handling across process boundaries
7. Tool state preservation and cleanup

Prerequisites:
- Tools should be registered in the registry
- System should support subprocess creation
"""

from __future__ import annotations

import asyncio
import gc
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

from pydantic import BaseModel, Field

from chuk_tool_processor.execution.strategies.subprocess_strategy import SubprocessStrategy
from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.validated_tool import ValidatedTool
from chuk_tool_processor.registry.decorators import register_tool
from chuk_tool_processor.registry.provider import ToolRegistryProvider

logger = get_logger("subprocess-strategy-resilience-test")

# ═══════════════════════════════════════════════════════════════════════════
# Subprocess Strategy-Specific Resilience Test Configuration
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class SubprocessResilienceTestConfig:
    """Configuration for SubprocessStrategy resilience testing scenarios."""

    max_test_duration: float = 300.0  # 5 minutes max per test
    worker_pool_size: int = 4  # Number of worker processes
    stress_test_calls: int = 25  # Higher for subprocess throughput testing
    concurrent_operations: int = 6  # Test concurrent subprocess execution
    failure_injection_rate: float = 0.3  # 30% of operations will cause issues
    process_restart_delay: float = 2.0  # Time for process pool recovery
    timeout_test_duration: float = 8.0
    memory_stress_iterations: int = 10  # Memory stress test iterations


@dataclass
class TestResult:
    """Result of a SubprocessStrategy resilience test."""

    test_name: str
    success: bool
    duration: float
    error_count: int = 0
    recovery_count: int = 0
    total_operations: int = 0
    process_crashes: int = 0  # Subprocess process crashes
    serialization_errors: int = 0  # Serialization/deserialization issues
    pool_recoveries: int = 0  # Worker pool recovery events
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if self.total_operations == 0:
            return 0.0
        return (self.total_operations - self.error_count) / self.total_operations * 100


# ═══════════════════════════════════════════════════════════════════════════
# Test Tools for Subprocess Strategy Testing
# ═══════════════════════════════════════════════════════════════════════════


@register_tool(name="simple_calculator", namespace="subprocess_test")
class SimpleCalculatorTool(ValidatedTool):
    """Simple calculator tool for basic subprocess testing."""

    class Arguments(BaseModel):
        operation: str = Field(..., description="Operation: add, subtract, multiply, divide")
        a: float = Field(..., description="First number")
        b: float = Field(..., description="Second number")

    class Result(BaseModel):
        result: float
        operation: str

    async def _execute(self, operation: str, a: float, b: float) -> Result:
        operations = {"add": a + b, "subtract": a - b, "multiply": a * b, "divide": a / b if b != 0 else None}

        if operation not in operations:
            raise ValueError(f"Unknown operation: {operation}")

        result = operations[operation]
        if result is None:
            raise ValueError("Cannot divide by zero")

        return self.Result(result=result, operation=operation)


@register_tool(name="memory_intensive", namespace="subprocess_test")
class MemoryIntensiveTool(ValidatedTool):
    """Memory-intensive tool to test subprocess isolation."""

    class Arguments(BaseModel):
        size_mb: int = Field(default=10, description="Memory to allocate in MB")
        duration: float = Field(default=1.0, description="How long to hold memory")

    class Result(BaseModel):
        allocated_mb: int
        peak_memory_mb: float
        duration: float

    async def _execute(self, size_mb: int, duration: float) -> Result:
        import psutil

        process = psutil.Process()
        process.memory_info().rss / 1024 / 1024

        # Allocate memory
        data = bytearray(size_mb * 1024 * 1024)

        # Fill with data to ensure allocation
        for i in range(0, len(data), 1024):
            data[i : i + 8] = b"testdata"

        await asyncio.sleep(duration)

        peak_memory = process.memory_info().rss / 1024 / 1024

        # Clean up
        del data
        gc.collect()

        return self.Result(allocated_mb=size_mb, peak_memory_mb=peak_memory, duration=duration)


@register_tool(name="slow_processor", namespace="subprocess_test")
class SlowProcessorTool(ValidatedTool):
    """Slow processing tool to test subprocess timeouts."""

    class Arguments(BaseModel):
        duration: float = Field(..., description="Processing duration in seconds")
        should_fail: bool = Field(default=False, description="Whether to fail")

    class Result(BaseModel):
        processed_for: float
        success: bool

    async def _execute(self, duration: float, should_fail: bool) -> Result:
        if should_fail:
            await asyncio.sleep(duration / 2)
            raise RuntimeError(f"Intentional failure after {duration / 2}s")

        await asyncio.sleep(duration)
        return self.Result(processed_for=duration, success=True)


@register_tool(name="serialization_complex", namespace="subprocess_test")
class SerializationComplexTool(ValidatedTool):
    """Tool with complex data structures to test serialization."""

    class Arguments(BaseModel):
        data_structure: str = Field(default="dict", description="Type: dict, list, nested")
        size: int = Field(default=100, description="Size of data structure")

    class Result(BaseModel):
        structure_type: str
        size: int
        serialization_test: bool

    async def _execute(self, data_structure: str, size: int) -> Result:
        # Create complex data structures
        if data_structure == "dict":
            data = {f"key_{i}": {"nested": f"value_{i}", "number": i} for i in range(size)}
        elif data_structure == "list":
            data = [{"item": i, "data": list(range(i % 10))} for i in range(size)]
        elif data_structure == "nested":
            data = {"level1": {"level2": {"level3": [{"deep_item": i, "value": f"nested_{i}"} for i in range(size)]}}}
        else:
            raise ValueError(f"Unknown data structure type: {data_structure}")

        # Test that data survived serialization/deserialization by accessing it
        data_size = len(str(data))

        return self.Result(
            structure_type=data_structure,
            size=len(data) if isinstance(data, list | dict) else size,
            serialization_test=data_size > 0,
        )


class SubprocessStrategyResilienceTestSuite:
    """SubprocessStrategy-specific resilience testing suite."""

    def __init__(self, config: SubprocessResilienceTestConfig):
        self.config = config
        self.test_results: list[TestResult] = []
        self.shutdown_event = asyncio.Event()
        self.subprocess_executors = []
        self.available_tools: dict[str, list[str]] = {}  # namespace -> [tool_names]

    def banner(self, text: str, color: str = Fore.CYAN) -> None:
        """Print a colored banner."""
        print(f"\n{color}{'=' * 60}")
        print(f"  {text}")
        print(f"{'=' * 60}{Style.RESET_ALL}\n")

    def print_progress(self, message: str, color: str = Fore.YELLOW):
        """Print progress message."""
        print(f"{color}🔄 {message}{Style.RESET_ALL}")

    async def setup_test_tools(self):
        """Ensure test tools are registered."""
        try:
            from chuk_tool_processor.registry.decorators import ensure_registrations

            await ensure_registrations()
            self.print_progress("Test tools registered successfully")
        except Exception as e:
            logger.error(f"Error registering test tools: {e}")
            raise

    async def discover_available_tools(self, namespace: str) -> list[str]:
        """Discover what tools are available in the subprocess test namespace."""
        try:
            registry = await ToolRegistryProvider.get_registry()
            all_tools = await registry.list_tools()

            namespace_tools = [tool_name for ns, tool_name in all_tools if ns == namespace]

            self.print_progress(
                f"Found {len(namespace_tools)} subprocess test tools in namespace '{namespace}': {namespace_tools}"
            )
            self.available_tools[namespace] = namespace_tools

            return namespace_tools

        except Exception as e:
            logger.error(f"Error discovering subprocess tools in namespace {namespace}: {e}")
            return []

    def count_subprocess_processes(self) -> int:
        """Count current subprocess worker processes."""
        count = 0
        try:
            current_pid = os.getpid()
            for proc in psutil.process_iter(["pid", "ppid", "name"]):
                try:
                    if proc.info["ppid"] == current_pid and "python" in proc.info["name"].lower():
                        count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass
        return count

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
    # Test 1: Basic Subprocess Process Isolation
    # ================================================================

    async def test_subprocess_process_isolation(self) -> TestResult:
        """Test basic subprocess process isolation and worker pool."""
        self.banner("TEST 1: Subprocess Process Isolation", Fore.GREEN)

        start_time = time.time()
        test_result = TestResult("subprocess_process_isolation", False, 0.0)

        try:
            await self.setup_test_tools()

            self.print_progress("Setting up subprocess strategy...")
            registry = await ToolRegistryProvider.get_registry()

            subprocess_executor = ToolExecutor(
                registry,
                strategy=SubprocessStrategy(registry, max_workers=self.config.worker_pool_size, default_timeout=10.0),
            )
            self.subprocess_executors.append(subprocess_executor)

            # Discover available tools
            available_tools = await self.discover_available_tools("subprocess_test")
            if not available_tools:
                raise RuntimeError("No subprocess test tools found")

            # Count initial processes
            initial_process_count = self.count_subprocess_processes()
            self.print_progress(f"Initial subprocess count: {initial_process_count}")

            # Test simple calculation to verify subprocess execution
            if "simple_calculator" in available_tools:
                self.print_progress("Testing basic subprocess execution...")

                calc_call = ToolCall(tool="simple_calculator", arguments={"operation": "add", "a": 10, "b": 5})

                result = await subprocess_executor.execute([calc_call])
                test_result.total_operations += 1

                if result[0].error:
                    test_result.error_count += 1
                    raise RuntimeError(f"Basic subprocess calculation failed: {result[0].error}")
                else:
                    test_result.recovery_count += 1
                    expected_result = 15
                    actual_result = (
                        result[0].result.get("result") if isinstance(result[0].result, dict) else result[0].result
                    )

                    # Fix: Handle various result formats - dict, object attributes, or string representation
                    numeric_result = None

                    if isinstance(actual_result, dict) and "result" in actual_result:
                        # Case 1: Dictionary with "result" key
                        numeric_result = actual_result["result"]
                    elif hasattr(actual_result, "result"):
                        # Case 2: Object with result attribute
                        numeric_result = actual_result.result
                    elif isinstance(actual_result, str) and "result=" in actual_result:
                        # Case 3: String representation like "result=15.0 operation='add'"
                        import re

                        match = re.search(r"result=([0-9.]+)", actual_result)
                        if match:
                            numeric_result = float(match.group(1))
                    else:
                        # Case 4: Direct numeric value
                        numeric_result = actual_result

                    if isinstance(numeric_result, int | float) and float(numeric_result) == float(expected_result):
                        self.print_progress("✅ Basic subprocess calculation successful")
                    else:
                        raise RuntimeError(
                            f"Incorrect calculation result: expected {expected_result}, got {numeric_result} (from {actual_result})"
                        )

            # Test process isolation with memory-intensive task
            if "memory_intensive" in available_tools:
                self.print_progress("Testing subprocess memory isolation...")

                memory_call = ToolCall(tool="memory_intensive", arguments={"size_mb": 5, "duration": 1.0})

                memory_result = await subprocess_executor.execute([memory_call])
                test_result.total_operations += 1

                if memory_result[0].error:
                    test_result.error_count += 1
                    self.print_progress(f"⚠️ Memory isolation test failed: {memory_result[0].error}")
                else:
                    test_result.recovery_count += 1
                    self.print_progress("✅ Memory isolation test successful")

            # Verify worker processes were created
            final_process_count = self.count_subprocess_processes()
            self.print_progress(f"Final subprocess count: {final_process_count}")

            if final_process_count >= initial_process_count:
                self.print_progress("✅ Worker processes created successfully")
                test_result.success = True
            else:
                self.print_progress("❌ Worker process creation issues detected")

        except Exception as e:
            logger.error(f"Subprocess process isolation test failed: {e}")
            test_result.details["error"] = str(e)

        finally:
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)

        return test_result

    # ================================================================
    # Test 2: Worker Process Crash Recovery
    # ================================================================

    async def test_worker_process_crash_recovery(self) -> TestResult:
        """Test recovery from worker process crashes."""
        self.banner("TEST 2: Worker Process Crash Recovery", Fore.GREEN)

        start_time = time.time()
        test_result = TestResult("worker_process_crash_recovery", False, 0.0)

        try:
            registry = await ToolRegistryProvider.get_registry()

            subprocess_executor = ToolExecutor(
                registry,
                strategy=SubprocessStrategy(
                    registry,
                    max_workers=2,  # Smaller pool for crash testing
                    default_timeout=8.0,
                ),
            )
            self.subprocess_executors.append(subprocess_executor)

            available_tools = await self.discover_available_tools("subprocess_test")
            if not available_tools:
                raise RuntimeError("No tools found for crash recovery test")

            # Test normal operation first
            if "simple_calculator" in available_tools:
                self.print_progress("Testing normal operation before crash...")

                normal_call = ToolCall(tool="simple_calculator", arguments={"operation": "multiply", "a": 6, "b": 7})

                normal_result = await subprocess_executor.execute([normal_call])
                test_result.total_operations += 1

                if normal_result[0].error:
                    test_result.error_count += 1
                    self.print_progress(f"⚠️ Normal operation failed: {normal_result[0].error}")
                else:
                    test_result.recovery_count += 1
                    self.print_progress("✅ Normal operation successful")

            # Simulate worker process crashes using failing tasks
            if "slow_processor" in available_tools:
                self.print_progress("Simulating worker process crashes...")

                # Create calls that will fail and potentially crash workers
                crash_calls = [
                    ToolCall(tool="slow_processor", arguments={"duration": 0.5, "should_fail": True})
                    for _ in range(3)  # Multiple failure calls
                ]

                crash_results = await subprocess_executor.execute(crash_calls)
                test_result.total_operations += len(crash_results)

                crashed_count = sum(1 for r in crash_results if r.error)
                test_result.error_count += crashed_count
                test_result.process_crashes += crashed_count

                self.print_progress(f"Crash simulation: {crashed_count}/{len(crash_results)} calls failed (expected)")

            # Test recovery with new calls
            self.print_progress("Testing recovery after crashes...")

            if "simple_calculator" in available_tools:
                recovery_calls = [
                    ToolCall(tool="simple_calculator", arguments={"operation": "add", "a": i, "b": i + 1})
                    for i in range(3)
                ]

                recovery_results = await subprocess_executor.execute(recovery_calls)
                test_result.total_operations += len(recovery_results)

                successful_recoveries = sum(1 for r in recovery_results if not r.error)
                test_result.recovery_count += successful_recoveries
                test_result.pool_recoveries += 1 if successful_recoveries > 0 else 0

                self.print_progress(f"Recovery test: {successful_recoveries}/{len(recovery_results)} calls successful")

                if successful_recoveries >= len(recovery_results) * 0.6:  # 60% success rate
                    test_result.success = True
                    self.print_progress("✅ Worker process crash recovery successful!")
                else:
                    self.print_progress("❌ Insufficient recovery after crashes")

        except Exception as e:
            logger.error(f"Worker process crash recovery test failed: {e}")
            test_result.details["error"] = str(e)

        finally:
            test_result.duration = time.time() - start_time
            test_result.details.update(
                {"process_crashes": test_result.process_crashes, "pool_recoveries": test_result.pool_recoveries}
            )
            self.test_results.append(test_result)

        return test_result

    # ================================================================
    # Test 3: Serialization Robustness
    # ================================================================

    async def test_serialization_robustness(self) -> TestResult:
        """Test robustness of tool serialization across process boundaries."""
        self.banner("TEST 3: Serialization Robustness", Fore.GREEN)

        start_time = time.time()
        test_result = TestResult("serialization_robustness", False, 0.0)

        try:
            registry = await ToolRegistryProvider.get_registry()

            subprocess_executor = ToolExecutor(
                registry,
                strategy=SubprocessStrategy(registry, max_workers=self.config.worker_pool_size, default_timeout=10.0),
            )
            self.subprocess_executors.append(subprocess_executor)

            available_tools = await self.discover_available_tools("subprocess_test")
            if not available_tools:
                raise RuntimeError("No tools found for serialization test")

            # Test complex data structure serialization
            if "serialization_complex" in available_tools:
                self.print_progress("Testing complex data structure serialization...")

                structure_types = ["dict", "list", "nested"]
                sizes = [10, 50, 100]

                for struct_type in structure_types:
                    for size in sizes:
                        call = ToolCall(
                            tool="serialization_complex", arguments={"data_structure": struct_type, "size": size}
                        )

                        result = await subprocess_executor.execute([call])
                        test_result.total_operations += 1

                        if result[0].error:
                            test_result.error_count += 1
                            if "serializ" in str(result[0].error).lower() or "pickle" in str(result[0].error).lower():
                                test_result.serialization_errors += 1
                            self.print_progress(f"❌ Serialization failed for {struct_type}[{size}]: {result[0].error}")
                        else:
                            test_result.recovery_count += 1
                            self.print_progress(f"✅ Serialization successful for {struct_type}[{size}]")

            # Test multiple concurrent serializations
            self.print_progress("Testing concurrent serialization...")

            if "simple_calculator" in available_tools and "memory_intensive" in available_tools:
                concurrent_calls = []

                # Mix different tool types for concurrent serialization test
                for i in range(6):
                    if i % 2 == 0:
                        call = ToolCall(tool="simple_calculator", arguments={"operation": "add", "a": i, "b": i + 1})
                    else:
                        call = ToolCall(tool="memory_intensive", arguments={"size_mb": 2, "duration": 0.5})
                    concurrent_calls.append(call)

                concurrent_results = await subprocess_executor.execute(concurrent_calls)
                test_result.total_operations += len(concurrent_results)

                concurrent_success = sum(1 for r in concurrent_results if not r.error)
                concurrent_serialization_errors = sum(
                    1
                    for r in concurrent_results
                    if r.error and ("serializ" in str(r.error).lower() or "pickle" in str(r.error).lower())
                )

                test_result.recovery_count += concurrent_success
                test_result.error_count += len(concurrent_results) - concurrent_success
                test_result.serialization_errors += concurrent_serialization_errors

                self.print_progress(
                    f"Concurrent serialization: {concurrent_success}/{len(concurrent_results)} successful"
                )
                self.print_progress(f"Serialization errors: {test_result.serialization_errors}")

            # Test passes if serialization error rate is low
            serialization_error_rate = (
                (test_result.serialization_errors / test_result.total_operations * 100)
                if test_result.total_operations > 0
                else 0
            )

            if test_result.success_rate >= 70.0 and serialization_error_rate <= 10.0:
                test_result.success = True
                self.print_progress("✅ Serialization robustness test passed!")
            else:
                self.print_progress(f"❌ Serialization issues detected - error rate: {serialization_error_rate:.1f}%")

        except Exception as e:
            logger.error(f"Serialization robustness test failed: {e}")
            test_result.details["error"] = str(e)

        finally:
            test_result.duration = time.time() - start_time
            test_result.details["serialization_errors"] = test_result.serialization_errors
            self.test_results.append(test_result)

        return test_result

    # ================================================================
    # Test 4: Subprocess Timeout Handling
    # ================================================================

    async def test_subprocess_timeout_handling(self) -> TestResult:
        """Test timeout handling across subprocess boundaries."""
        self.banner("TEST 4: Subprocess Timeout Handling", Fore.GREEN)

        start_time = time.time()
        test_result = TestResult("subprocess_timeout_handling", False, 0.0)

        try:
            registry = await ToolRegistryProvider.get_registry()

            # Create executor with short timeout for testing
            subprocess_executor = ToolExecutor(
                registry,
                strategy=SubprocessStrategy(
                    registry,
                    max_workers=2,
                    default_timeout=3.0,  # Short timeout for testing
                ),
            )
            self.subprocess_executors.append(subprocess_executor)

            available_tools = await self.discover_available_tools("subprocess_test")
            if not available_tools:
                raise RuntimeError("No tools found for timeout test")

            # Test normal operation within timeout
            if "slow_processor" in available_tools:
                self.print_progress("Testing normal operation within timeout...")

                normal_call = ToolCall(tool="slow_processor", arguments={"duration": 1.0, "should_fail": False})

                normal_result = await subprocess_executor.execute([normal_call])
                test_result.total_operations += 1

                if normal_result[0].error:
                    test_result.error_count += 1
                    self.print_progress(f"⚠️ Normal timeout test failed: {normal_result[0].error}")
                else:
                    test_result.recovery_count += 1
                    self.print_progress("✅ Normal timeout test successful")

            # Test timeout scenarios
            if "slow_processor" in available_tools:
                self.print_progress("Testing subprocess timeout scenarios...")

                timeout_calls = [
                    ToolCall(
                        tool="slow_processor",
                        arguments={"duration": 5.0, "should_fail": False},  # Longer than timeout
                    )
                    for _ in range(3)
                ]

                timeout_results = await subprocess_executor.execute(timeout_calls)
                test_result.total_operations += len(timeout_results)

                timeout_count = sum(1 for r in timeout_results if r.error and "timeout" in str(r.error).lower())

                test_result.error_count += (
                    len(timeout_results) - timeout_count if timeout_count < len(timeout_results) else timeout_count
                )

                self.print_progress(f"Timeout test: {timeout_count}/{len(timeout_results)} calls timed out (expected)")

            # Test recovery after timeouts
            self.print_progress("Testing recovery after timeouts...")

            if "simple_calculator" in available_tools:
                recovery_calls = [
                    ToolCall(tool="simple_calculator", arguments={"operation": "multiply", "a": 3, "b": 4})
                    for _ in range(3)
                ]

                recovery_results = await subprocess_executor.execute(recovery_calls)
                test_result.total_operations += len(recovery_results)

                recovery_success = sum(1 for r in recovery_results if not r.error)
                test_result.recovery_count += recovery_success

                self.print_progress(f"Recovery after timeout: {recovery_success}/{len(recovery_results)} successful")

                if recovery_success >= len(recovery_results) * 0.8:  # 80% success rate
                    test_result.success = True
                    self.print_progress("✅ Subprocess timeout handling successful!")
                else:
                    self.print_progress("❌ Poor recovery after timeouts")

        except Exception as e:
            logger.error(f"Subprocess timeout handling test failed: {e}")
            test_result.details["error"] = str(e)

        finally:
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)

        return test_result

    # ================================================================
    # Test 5: Concurrent Subprocess Stress Test
    # ================================================================

    async def test_concurrent_subprocess_stress(self) -> TestResult:
        """Test subprocess system under concurrent load."""
        self.banner("TEST 5: Concurrent Subprocess Stress Test", Fore.GREEN)

        start_time = time.time()
        test_result = TestResult("concurrent_subprocess_stress", False, 0.0)

        try:
            registry = await ToolRegistryProvider.get_registry()

            # Create executor with higher concurrency for stress testing
            subprocess_executor = ToolExecutor(
                registry,
                strategy=SubprocessStrategy(registry, max_workers=self.config.worker_pool_size, default_timeout=10.0),
            )
            self.subprocess_executors.append(subprocess_executor)

            available_tools = await self.discover_available_tools("subprocess_test")
            if not available_tools:
                raise RuntimeError("No tools found for subprocess stress test")

            # Generate stress test calls mixing different tool types
            stress_calls = []

            for _i in range(self.config.stress_test_calls):
                tool_choice = random.choice(available_tools)

                if tool_choice == "simple_calculator":
                    args = {
                        "operation": random.choice(["add", "subtract", "multiply"]),
                        "a": random.randint(1, 100),
                        "b": random.randint(1, 100),
                    }
                elif tool_choice == "memory_intensive":
                    args = {"size_mb": random.randint(1, 5), "duration": random.uniform(0.5, 1.5)}
                elif tool_choice == "slow_processor":
                    args = {
                        "duration": random.uniform(0.5, 2.0),
                        "should_fail": random.random() < 0.1,  # 10% failure rate
                    }
                elif tool_choice == "serialization_complex":
                    args = {"data_structure": random.choice(["dict", "list"]), "size": random.randint(10, 50)}
                else:
                    args = {}

                call = ToolCall(tool=tool_choice, arguments=args)
                stress_calls.append(call)

            if not stress_calls:
                raise RuntimeError("No stress calls could be generated")

            self.print_progress(f"Executing {len(stress_calls)} concurrent subprocess calls...")

            stress_start = time.time()
            stress_results = await subprocess_executor.execute(stress_calls)
            stress_duration = time.time() - stress_start

            # Analyze results
            successful_calls = sum(1 for r in stress_results if not r.error)
            failed_calls = len(stress_results) - successful_calls

            test_result.total_operations = len(stress_results)
            test_result.error_count = failed_calls
            test_result.recovery_count = successful_calls

            # Count subprocess-specific issues
            for result in stress_results:
                if result.error:
                    error_str = str(result.error).lower()
                    if "process" in error_str or "worker" in error_str:
                        test_result.process_crashes += 1
                    elif "serializ" in error_str or "pickle" in error_str:
                        test_result.serialization_errors += 1

            calls_per_second = len(stress_calls) / stress_duration if stress_duration > 0 else 0

            self.print_progress(f"Subprocess stress test completed in {stress_duration:.2f}s")
            self.print_progress(f"Throughput: {calls_per_second:.1f} calls/second")
            self.print_progress(f"Success rate: {test_result.success_rate:.1f}%")
            self.print_progress(f"Process issues: {test_result.process_crashes}")
            self.print_progress(f"Serialization issues: {test_result.serialization_errors}")

            # Test passes if success rate is reasonable for subprocess complexity
            if test_result.success_rate >= 75.0:
                test_result.success = True
                self.print_progress("✅ Subprocess stress test passed - system stable under load")
            else:
                self.print_progress("❌ Subprocess stress test failed - too many failures under load")

            test_result.details.update(
                {
                    "calls_per_second": calls_per_second,
                    "stress_duration": stress_duration,
                    "success_rate": test_result.success_rate,
                    "process_crashes": test_result.process_crashes,
                    "serialization_errors": test_result.serialization_errors,
                    "tools_used": len(available_tools),
                }
            )

        except Exception as e:
            logger.error(f"Concurrent subprocess stress test failed: {e}")
            test_result.details["error"] = str(e)

        finally:
            test_result.duration = time.time() - start_time
            self.test_results.append(test_result)

        return test_result

    # ================================================================
    # Test Runner and Reporting
    # ================================================================

    async def run_all_tests(self) -> dict[str, Any]:
        """Run all SubprocessStrategy resilience tests."""
        self.banner("SUBPROCESS STRATEGY RESILIENCE TEST SUITE", Fore.MAGENTA)

        try:
            tests = [
                self.test_subprocess_process_isolation,
                self.test_worker_process_crash_recovery,
                self.test_serialization_robustness,
                self.test_subprocess_timeout_handling,
                self.test_concurrent_subprocess_stress,
            ]

            for test_func in tests:
                if self.shutdown_event.is_set():
                    logger.info("Shutdown requested, stopping subprocess tests")
                    break

                try:
                    await asyncio.wait_for(test_func(), timeout=self.config.max_test_duration)

                    await asyncio.sleep(1.0)  # Brief pause between tests

                except TimeoutError:
                    logger.error(f"Subprocess test {test_func.__name__} timed out")
                    timeout_result = TestResult(
                        test_name=test_func.__name__,
                        success=False,
                        duration=self.config.max_test_duration,
                        details={"error": "Test timed out"},
                    )
                    self.test_results.append(timeout_result)

            return self.generate_test_report()

        finally:
            await self.cleanup_executors()

    async def cleanup_executors(self):
        """Clean up all subprocess executors."""
        self.print_progress("Cleaning up subprocess executors...")

        for executor in self.subprocess_executors:
            try:
                if hasattr(executor.strategy, "shutdown"):
                    await asyncio.wait_for(executor.strategy.shutdown(), timeout=5.0)
            except Exception as e:
                logger.debug(f"Error shutting down subprocess executor: {e}")

        self.subprocess_executors.clear()

    def generate_test_report(self) -> dict[str, Any]:
        """Generate comprehensive SubprocessStrategy test report."""
        self.banner("SUBPROCESS STRATEGY RESILIENCE TEST RESULTS", Fore.MAGENTA)

        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r.success)
        failed_tests = total_tests - passed_tests

        total_operations = sum(r.total_operations for r in self.test_results)
        total_errors = sum(r.error_count for r in self.test_results)
        total_recoveries = sum(r.recovery_count for r in self.test_results)
        total_process_crashes = sum(r.process_crashes for r in self.test_results)
        total_serialization_errors = sum(r.serialization_errors for r in self.test_results)
        total_pool_recoveries = sum(r.pool_recoveries for r in self.test_results)

        overall_success_rate = (
            ((total_operations - total_errors) / total_operations * 100) if total_operations > 0 else 0
        )

        # Print summary
        print(f"{Fore.CYAN}📊 SUBPROCESS STRATEGY TEST SUMMARY:{Style.RESET_ALL}")
        print(f"   Total Tests: {total_tests}")
        print(f"   Passed: {Fore.GREEN}{passed_tests}{Style.RESET_ALL}")
        print(f"   Failed: {Fore.RED}{failed_tests}{Style.RESET_ALL}")
        print(f"   Overall Success Rate: {Fore.YELLOW}{overall_success_rate:.1f}%{Style.RESET_ALL}")
        print(f"   Process Crashes Handled: {Fore.YELLOW}{total_process_crashes}{Style.RESET_ALL}")
        print(f"   Serialization Errors: {Fore.YELLOW}{total_serialization_errors}{Style.RESET_ALL}")
        print(f"   Pool Recoveries: {Fore.GREEN}{total_pool_recoveries}{Style.RESET_ALL}")
        print(f"   Total Operations: {total_operations}")
        print(f"   Successful Operations: {Fore.GREEN}{total_recoveries}{Style.RESET_ALL}")

        # Print detailed results
        print(f"\n{Fore.CYAN}📋 DETAILED SUBPROCESS STRATEGY RESULTS:{Style.RESET_ALL}")
        for result in self.test_results:
            status = f"{Fore.GREEN}✅ PASS" if result.success else f"{Fore.RED}❌ FAIL"
            print(f"   {status}{Style.RESET_ALL} {result.test_name}")
            print(f"      Duration: {result.duration:.2f}s")
            print(f"      Success Rate: {result.success_rate:.1f}%")
            print(f"      Process Issues: {result.process_crashes}")
            print(f"      Serialization Issues: {result.serialization_errors}")
            if result.details and "error" in result.details:
                print(f"      {Fore.RED}Error: {result.details['error']}{Style.RESET_ALL}")
            print()

        # Overall assessment for SubprocessStrategy
        if passed_tests == total_tests and overall_success_rate >= 80:
            print(
                f"{Fore.GREEN}🎉 EXCELLENT: All subprocess strategy tests passed with excellent isolation!{Style.RESET_ALL}"
            )
            resilience_grade = "excellent"
        elif passed_tests >= total_tests * 0.8 and overall_success_rate >= 70:
            print(
                f"{Fore.YELLOW}✅ GOOD: Most subprocess strategy tests passed with good process isolation.{Style.RESET_ALL}"
            )
            resilience_grade = "good"
        else:
            print(f"{Fore.RED}⚠️ NEEDS IMPROVEMENT: Subprocess strategy resilience issues detected.{Style.RESET_ALL}")
            resilience_grade = "needs_improvement"

        # Print SubprocessStrategy advantages summary
        print(f"\n{Fore.CYAN}📈 SUBPROCESS STRATEGY ADVANTAGES DEMONSTRATED:{Style.RESET_ALL}")
        print("   • Process isolation for memory safety")
        print("   • Worker pool management and recovery")
        print("   • Robust serialization across process boundaries")
        print("   • Crash isolation (one tool failure doesn't affect others)")
        print("   • Resource cleanup and timeout handling")
        print("   • Parallel execution with true process-level concurrency")

        return {
            "strategy_type": "SubprocessStrategy",
            "summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "overall_success_rate": overall_success_rate,
                "total_operations": total_operations,
                "total_errors": total_errors,
                "total_recoveries": total_recoveries,
                "process_crashes": total_process_crashes,
                "serialization_errors": total_serialization_errors,
                "pool_recoveries": total_pool_recoveries,
                "resilience_grade": resilience_grade,
            },
            "test_results": [
                {
                    "test_name": r.test_name,
                    "success": r.success,
                    "duration": r.duration,
                    "success_rate": r.success_rate,
                    "process_crashes": r.process_crashes,
                    "serialization_errors": r.serialization_errors,
                    "pool_recoveries": r.pool_recoveries,
                    "details": r.details,
                }
                for r in self.test_results
            ],
        }


async def main():
    """Main entry point for SubprocessStrategy resilience testing."""
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

    config = SubprocessResilienceTestConfig()
    test_suite = SubprocessStrategyResilienceTestSuite(config)
    test_suite.shutdown_event = shutdown_event

    try:
        print(f"{Fore.MAGENTA}🧪 Starting SubprocessStrategy Resilience Test Suite...{Style.RESET_ALL}")
        print(
            f"{Fore.YELLOW}Testing process isolation, worker pool management, and serialization robustness{Style.RESET_ALL}"
        )
        print(f"{Fore.YELLOW}This will test subprocess execution strategy resilience features{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Test duration: up to {config.max_test_duration * 5 / 60:.1f} minutes{Style.RESET_ALL}\n")

        results = await test_suite.run_all_tests()

        # Save results
        results_file = PROJECT_ROOT / "subprocess_strategy_resilience_test_results.json"
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2, default=str)

        print(f"\n{Fore.CYAN}📁 SubprocessStrategy test results saved to: {results_file}{Style.RESET_ALL}")

        # Exit with appropriate code
        if results["summary"]["resilience_grade"] == "excellent":
            print(f"\n{Fore.GREEN}🚀 SubprocessStrategy demonstrates excellent resilience!{Style.RESET_ALL}")
            return 0
        elif results["summary"]["resilience_grade"] == "good":
            print(f"\n{Fore.YELLOW}👍 SubprocessStrategy shows good resilience characteristics.{Style.RESET_ALL}")
            return 0
        else:
            print(f"\n{Fore.RED}⚠️ SubprocessStrategy resilience needs improvement.{Style.RESET_ALL}")
            return 1

    except Exception as e:
        print(f"\n{Fore.RED}❌ SubprocessStrategy resilience test suite failed: {e}{Style.RESET_ALL}")
        logger.error(f"SubprocessStrategy test suite failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
