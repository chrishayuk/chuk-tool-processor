#!/usr/bin/env python
# examples/timeout_bug_demo.py
"""
Demonstrate the timeout bug where configured timeouts are not respected.
"""

import asyncio
import inspect
import sys
import time
from pathlib import Path
from unittest.mock import patch

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.registry.decorators import register_tool
from chuk_tool_processor.registry.provider import ToolRegistryProvider

# Store original wait_for
original_wait_for = asyncio.wait_for


def get_caller_info():
    """Get information about the caller for debugging."""
    frame = inspect.currentframe()
    try:
        # Go up the stack to find the actual caller
        caller_frame = frame.f_back.f_back  # Skip wrapper function
        filename = Path(caller_frame.f_code.co_filename).name
        function = caller_frame.f_code.co_name
        line = caller_frame.f_lineno
        return f"{filename}:{line}:{function}"
    finally:
        del frame


async def debug_wait_for(coro, timeout=None):
    """Debug wrapper for asyncio.wait_for to trace timeout values."""
    caller = get_caller_info()
    print(f"    🕐 wait_for(timeout={timeout}s) called from {caller}")
    return await original_wait_for(coro, timeout)


@register_tool(name="slow_tool")
class SlowTool:
    """A tool that takes a specific amount of time to complete."""

    async def execute(self, delay: float = 5.0, message: str = "completed") -> dict:
        print(f"    🐌 SlowTool starting (will take {delay}s)...")
        await asyncio.sleep(delay)
        print(f"    ✅ SlowTool completed after {delay}s")
        return {"message": message, "delay": delay}


async def test_timeout_bug():
    """Test various timeout scenarios to expose the bug."""

    print("=== TIMEOUT BUG DEMONSTRATION ===\n")

    # Patch asyncio.wait_for to trace calls
    with patch("asyncio.wait_for", debug_wait_for):
        # Also patch in specific modules
        with patch("chuk_tool_processor.execution.strategies.inprocess_strategy.asyncio.wait_for", debug_wait_for):
            # Initialize registry
            from chuk_tool_processor.registry.decorators import ensure_registrations

            await ensure_registrations()
            registry = await ToolRegistryProvider.get_registry()

            # Test 1: Short timeout that should be respected
            print("📋 TEST 1: InProcessStrategy with 2s timeout vs 5s tool")
            print("   Expected: Should timeout after 2s")
            print("   Actual behavior:")

            strategy = InProcessStrategy(
                registry=registry,
                default_timeout=2.0,  # 2 second timeout
            )

            executor = ToolExecutor(registry=registry, strategy=strategy)

            call = ToolCall(tool="slow_tool", arguments={"delay": 5.0, "message": "This should timeout"})

            print(f"   📊 Strategy default_timeout: {strategy.default_timeout}s")

            start_time = time.time()
            try:
                results = await executor.execute([call])
                duration = time.time() - start_time
                result = results[0]

                print(f"   📈 Total duration: {duration:.3f}s")
                print(f"   📝 Result: {result.result if not result.error else f'ERROR: {result.error}'}")

                if duration > 3.0:  # If it took more than 3s, timeout wasn't respected
                    print(f"   🚨 BUG DETECTED: Took {duration:.3f}s but timeout was 2.0s!")
                else:
                    print(f"   ✅ Timeout respected: {duration:.3f}s <= 2.0s")

            except Exception as e:
                duration = time.time() - start_time
                print(f"   ❌ Exception after {duration:.3f}s: {e}")

            print()

            # Test 2: Explicit timeout parameter
            print("📋 TEST 2: Explicit timeout parameter (1s) vs 5s tool")
            print("   Expected: Should timeout after 1s")
            print("   Actual behavior:")

            start_time = time.time()
            try:
                results = await executor.execute([call], timeout=1.0)  # Explicit 1s timeout
                duration = time.time() - start_time
                result = results[0]

                print(f"   📈 Total duration: {duration:.3f}s")
                print(f"   📝 Result: {result.result if not result.error else f'ERROR: {result.error}'}")

                if duration > 2.0:  # If it took more than 2s, timeout wasn't respected
                    print(f"   🚨 BUG DETECTED: Took {duration:.3f}s but timeout was 1.0s!")
                else:
                    print(f"   ✅ Timeout respected: {duration:.3f}s <= 1.0s")

            except Exception as e:
                duration = time.time() - start_time
                print(f"   ❌ Exception after {duration:.3f}s: {e}")

            print()

            # Test 3: Test the strategy directly
            print("📋 TEST 3: Testing strategy.run() directly with 1s timeout")
            print("   Expected: Should timeout after 1s")
            print("   Actual behavior:")

            start_time = time.time()
            try:
                results = await strategy.run([call], timeout=1.0)
                duration = time.time() - start_time
                result = results[0]

                print(f"   📈 Total duration: {duration:.3f}s")
                print(f"   📝 Result: {result.result if not result.error else f'ERROR: {result.error}'}")

                if duration > 2.0:
                    print(f"   🚨 BUG DETECTED: Took {duration:.3f}s but timeout was 1.0s!")
                else:
                    print(f"   ✅ Timeout respected: {duration:.3f}s <= 1.0s")

            except Exception as e:
                duration = time.time() - start_time
                print(f"   ❌ Exception after {duration:.3f}s: {e}")

            print()

            # Test 4: Check what happens with a tool that completes quickly
            print("📋 TEST 4: Fast tool with 1s timeout (should work)")
            print("   Expected: Should complete quickly")
            print("   Actual behavior:")

            fast_call = ToolCall(tool="slow_tool", arguments={"delay": 0.1, "message": "Quick completion"})

            start_time = time.time()
            try:
                results = await executor.execute([fast_call], timeout=1.0)
                duration = time.time() - start_time
                result = results[0]

                print(f"   📈 Total duration: {duration:.3f}s")
                print(f"   📝 Result: {result.result if not result.error else f'ERROR: {result.error}'}")
                print("   ✅ Fast tool worked as expected")

            except Exception as e:
                duration = time.time() - start_time
                print(f"   ❌ Exception after {duration:.3f}s: {e}")

            print()

            # Test 5: Check what timeout values are actually being used
            print("📋 TEST 5: Inspect timeout values in strategy")
            print(f"   Strategy.default_timeout: {strategy.default_timeout}")
            print(f"   Strategy._sem: {strategy._sem}")

            # Let's also check the private methods
            if hasattr(strategy, "_execute_single_call"):
                print("   Strategy has _execute_single_call method")
            if hasattr(strategy, "_run_with_timeout"):
                print("   Strategy has _run_with_timeout method")

            print()

            print("=== SUMMARY ===")
            print("If any tests show 'BUG DETECTED', then timeouts are not being respected properly.")
            print("Look for calls to wait_for with timeout values that don't match what was configured.")


if __name__ == "__main__":
    asyncio.run(test_timeout_bug())
