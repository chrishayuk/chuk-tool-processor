#!/usr/bin/env python
"""
Generate metrics for Grafana dashboard screenshot.
Runs continuously and generates realistic tool execution patterns.
"""

import asyncio
import random
from chuk_tool_processor.observability import setup_observability
from chuk_tool_processor.core.processor import ToolProcessor
from chuk_tool_processor.registry import initialize, register_tool

# Register some test tools
@register_tool(name="calculator")
class CalculatorTool:
    async def execute(self, operation: str, a: float, b: float) -> dict:
        await asyncio.sleep(random.uniform(0.01, 0.05))
        ops = {"add": a + b, "multiply": a * b, "subtract": a - b}
        return {"result": ops.get(operation, 0)}

@register_tool(name="weather")
class WeatherTool:
    async def execute(self, location: str) -> dict:
        await asyncio.sleep(random.uniform(0.05, 0.15))
        return {"temperature": random.randint(60, 85), "conditions": "sunny"}

@register_tool(name="database")
class DatabaseTool:
    def __init__(self):
        self.fail_count = 0

    async def execute(self, query: str) -> dict:
        await asyncio.sleep(random.uniform(0.1, 0.3))
        # Fail occasionally to show circuit breaker
        self.fail_count += 1
        if self.fail_count % 20 == 0:
            raise ValueError("Database connection timeout")
        return {"rows": random.randint(0, 100), "query": query}

@register_tool(name="api_call")
class APITool:
    async def execute(self, endpoint: str) -> dict:
        await asyncio.sleep(random.uniform(0.05, 0.2))
        return {"status": 200, "data": {"endpoint": endpoint}}

@register_tool(name="slow_tool")
class SlowTool:
    async def execute(self, task: str) -> dict:
        await asyncio.sleep(random.uniform(0.5, 1.0))
        return {"completed": task, "duration": "long"}

async def main():
    print("Setting up observability...")
    setup_observability(
        service_name="metrics-generator",
        enable_tracing=True,
        enable_metrics=True,
        metrics_port=9090
    )

    print("Initializing processor...")
    await initialize()
    processor = ToolProcessor(
        enable_caching=True,
        cache_ttl=60,
        enable_retries=True,
        max_retries=3,
        enable_rate_limiting=True,
        global_rate_limit=100,
        enable_circuit_breaker=True,
        circuit_breaker_threshold=5,
        circuit_breaker_timeout=30.0
    )

    print("Generating metrics... (press Ctrl+C to stop)")
    print("Metrics available at http://localhost:9090/metrics")

    iteration = 0
    while True:
        iteration += 1

        # Mix of different tool calls with different patterns
        tool_calls = []

        # Calculator - high frequency, low latency
        for _ in range(random.randint(3, 7)):
            tool_calls.append(
                f'<tool name="calculator" args=\'{{"operation":"add","a":{random.randint(1,100)},"b":{random.randint(1,100)}}}\'/>'
            )

        # Weather - medium frequency
        for _ in range(random.randint(1, 3)):
            cities = ["San Francisco", "New York", "London", "Tokyo", "Sydney"]
            tool_calls.append(
                f'<tool name="weather" args=\'{{"location":"{random.choice(cities)}"}}\'/>'
            )

        # Database - lower frequency, higher latency
        if random.random() > 0.3:
            queries = ["SELECT * FROM users", "SELECT COUNT(*) FROM orders", "UPDATE inventory"]
            tool_calls.append(
                f'<tool name="database" args=\'{{"query":"{random.choice(queries)}"}}\'/>'
            )

        # API calls - medium frequency
        if random.random() > 0.4:
            endpoints = ["/api/users", "/api/products", "/api/orders", "/api/stats"]
            tool_calls.append(
                f'<tool name="api_call" args=\'{{"endpoint":"{random.choice(endpoints)}"}}\'/>'
            )

        # Slow tool - occasional
        if random.random() > 0.8:
            tool_calls.append(
                '<tool name="slow_tool" args=\'{"task":"process_batch"}\'/>'
            )

        # Execute all tool calls
        try:
            combined = "\n".join(tool_calls)
            results = await processor.process(combined)

            success = sum(1 for r in results if not r.error)
            errors = sum(1 for r in results if r.error)
            cached = sum(1 for r in results if r.cached)

            if iteration % 10 == 0:
                print(f"Iteration {iteration}: {success} success, {errors} errors, {cached} cached")
        except Exception as e:
            print(f"Error: {e}")

        # Wait a bit between batches
        await asyncio.sleep(random.uniform(0.5, 2.0))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopping metrics generation...")
