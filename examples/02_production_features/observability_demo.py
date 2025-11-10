#!/usr/bin/env python
"""
Observability Demo - OpenTelemetry + Prometheus Integration

This example demonstrates the drop-in OpenTelemetry tracing and Prometheus metrics
integration in chuk-tool-processor.

Prerequisites:
    pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp prometheus-client

Running the demo:
    1. Start an OTEL collector (optional, for tracing):
       docker run -p 4317:4317 otel/opentelemetry-collector

    2. Run this example:
       python examples/observability_demo.py

    3. View Prometheus metrics:
       curl http://localhost:9090/metrics

What you'll see:
    - OpenTelemetry spans for tool execution, caching, retries, circuit breaker
    - Prometheus metrics exported at http://localhost:9090/metrics
    - Automatic instrumentation of all tool operations
"""

import asyncio
import time

from chuk_tool_processor.core.processor import ToolProcessor
from chuk_tool_processor.observability import setup_observability
from chuk_tool_processor.registry import initialize, register_tool


# ------------------------------------------------------------------
# Example tool with retries and caching
# ------------------------------------------------------------------
@register_tool(name="slow_calculator")
class SlowCalculatorTool:
    """
    A calculator tool that simulates slow operations.

    This tool demonstrates observability features:
    - Execution spans
    - Cache hits/misses
    - Retry attempts
    """

    def __init__(self):
        self.call_count = 0

    async def execute(self, operation: str, a: float, b: float) -> dict:
        """Execute a slow calculation."""
        self.call_count += 1

        # Simulate slow operation
        await asyncio.sleep(0.5)

        # Fail first 2 attempts to demonstrate retries
        if self.call_count <= 2:
            raise ValueError(f"Simulated failure (attempt {self.call_count})")

        # Calculate result
        ops = {
            "add": a + b,
            "subtract": a - b,
            "multiply": a * b,
            "divide": a / b if b != 0 else None,
        }

        if operation not in ops:
            raise ValueError(f"Unsupported operation: {operation}")

        return {"result": ops[operation], "operation": operation}


# ------------------------------------------------------------------
# Main demo
# ------------------------------------------------------------------
async def main():
    print("=" * 70)
    print("OpenTelemetry + Prometheus Observability Demo")
    print("=" * 70)
    print()

    # ------------------------------------------------------------------
    # Step 1: Setup observability
    # ------------------------------------------------------------------
    print("Step 1: Initializing observability...")
    print()

    status = setup_observability(
        service_name="tool-processor-demo",
        enable_tracing=True,
        enable_metrics=True,
        metrics_port=9090,
    )

    print(f"  • Tracing enabled: {status['tracing_enabled']}")
    print(f"  • Metrics enabled: {status['metrics_enabled']}")
    print(f"  • Metrics server started: {status['metrics_server_started']}")

    if status["metrics_server_started"]:
        print("  • Metrics endpoint: http://localhost:9090/metrics")

    print()

    # ------------------------------------------------------------------
    # Step 2: Initialize registry and processor
    # ------------------------------------------------------------------
    print("Step 2: Initializing tool processor...")
    print()

    await initialize()

    # Create processor with production features enabled
    processor = ToolProcessor(
        enable_caching=True,  # Enable caching (will create cache spans)
        cache_ttl=300,  # 5 minute cache
        enable_retries=True,  # Enable retries (will create retry spans)
        max_retries=3,  # Up to 3 retry attempts
        enable_circuit_breaker=True,  # Enable circuit breaker (will track state)
        enable_rate_limiting=True,  # Enable rate limiting (will track checks)
        global_rate_limit=60,  # 60 requests/min
    )

    print("  • Caching enabled (TTL: 300s)")
    print("  • Retries enabled (max: 3)")
    print("  • Circuit breaker enabled")
    print("  • Rate limiting enabled (60 req/min)")
    print()

    # ------------------------------------------------------------------
    # Step 3: Execute tool calls (demonstrates all observability features)
    # ------------------------------------------------------------------
    print("Step 3: Executing tool calls...")
    print()

    # First call - will fail and retry, then succeed
    print("  [1] First call (will retry due to simulated failures)...")
    result1 = await processor.process('<tool name="slow_calculator" args=\'{"operation": "add", "a": 10, "b": 5}\'/>')

    if result1[0].error:
        print(f"      ✗ Error: {result1[0].error}")
    else:
        print(f"      ✓ Result: {result1[0].result}")
        print(f"      • Attempts: {result1[0].attempts}")
        print(f"      • Duration: {result1[0].duration:.3f}s")
        print(f"      • Cached: {result1[0].cached}")

    print()

    # Small delay to show separate operations
    await asyncio.sleep(1)

    # Second call - same arguments, should hit cache
    print("  [2] Second call (should hit cache)...")
    result2 = await processor.process('<tool name="slow_calculator" args=\'{"operation": "add", "a": 10, "b": 5}\'/>')

    if result2[0].error:
        print(f"      ✗ Error: {result2[0].error}")
    else:
        print(f"      ✓ Result: {result2[0].result}")
        print(f"      • Duration: {result2[0].duration:.3f}s")
        print(f"      • Cached: {result2[0].cached}")

    print()

    # Third call - different arguments, will execute fresh
    print("  [3] Third call (different arguments)...")
    result3 = await processor.process(
        '<tool name="slow_calculator" args=\'{"operation": "multiply", "a": 7, "b": 6}\'/>'
    )

    if result3[0].error:
        print(f"      ✗ Error: {result3[0].error}")
    else:
        print(f"      ✓ Result: {result3[0].result}")
        print(f"      • Duration: {result3[0].duration:.3f}s")
        print(f"      • Cached: {result3[0].cached}")

    print()

    # ------------------------------------------------------------------
    # Step 4: View observability data
    # ------------------------------------------------------------------
    print("=" * 70)
    print("Observability Data Generated")
    print("=" * 70)
    print()

    print("OpenTelemetry Spans Created:")
    print("  • tool.execute - Main tool execution spans")
    print("  • tool.retry.attempt - Retry attempt spans (3 attempts for first call)")
    print("  • tool.cache.lookup - Cache lookup operations")
    print("  • tool.cache.set - Cache set operations")
    print("  • tool.circuit_breaker.check - Circuit breaker state checks")
    print("  • tool.rate_limit.check - Rate limit checks")
    print()

    print("Prometheus Metrics Available:")
    print("  • tool_executions_total{tool,namespace,status}")
    print("  • tool_execution_duration_seconds{tool,namespace}")
    print("  • tool_cache_operations_total{tool,operation,result}")
    print("  • tool_retry_attempts_total{tool,attempt,success}")
    print("  • tool_circuit_breaker_state{tool}")
    print("  • tool_circuit_breaker_failures_total{tool}")
    print("  • tool_rate_limit_checks_total{tool,allowed}")
    print()

    if status["metrics_server_started"]:
        print("View metrics at: http://localhost:9090/metrics")
        print()
        print("Example queries:")
        print('  curl http://localhost:9090/metrics | grep "tool_executions_total"')
        print('  curl http://localhost:9090/metrics | grep "tool_cache_operations"')
        print('  curl http://localhost:9090/metrics | grep "tool_retry_attempts"')
        print()

    print("Traces exported to OTEL collector at: http://localhost:4317")
    print("(if running - see docker command in docstring)")
    print()

    # Keep server running for a bit so you can view metrics
    print("Keeping metrics server running for 30 seconds...")
    print("Press Ctrl+C to exit earlier")
    print()

    try:
        await asyncio.sleep(30)
    except KeyboardInterrupt:
        print("\nShutting down...")

    print()
    print("Demo complete!")


if __name__ == "__main__":
    asyncio.run(main())
