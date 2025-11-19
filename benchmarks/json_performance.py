#!/usr/bin/env python3
"""
JSON Performance Benchmark - Compare orjson vs stdlib json

Measures the performance difference between:
1. orjson (fast C implementation)
2. stdlib json (pure Python)

Focuses on tool processor specific operations:
- Tool call parsing (deserialization)
- Tool result serialization
- Complex nested arguments
"""

import json as stdlib_json
import logging
import os
import sys
import time
from pathlib import Path

# Suppress noisy logging
os.environ["CHUK_LOG_LEVEL"] = "ERROR"
logging.getLogger("chuk_tool_processor").setLevel(logging.ERROR)

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chuk_tool_processor.utils import fast_json  # noqa: E402

# Test data - realistic tool call payloads
SIMPLE_TOOL_CALL = {"name": "get_weather", "arguments": {"location": "San Francisco", "units": "celsius"}}

COMPLEX_TOOL_CALL = {
    "name": "database_query",
    "arguments": {
        "query": "SELECT * FROM users WHERE created_at > '2024-01-01' AND status IN ('active', 'pending')",
        "limit": 100,
        "offset": 0,
        "filters": {
            "role": ["admin", "user", "moderator"],
            "metadata": {
                "tags": ["important", "verified", "premium"],
                "score_range": {"min": 0, "max": 100},
                "nested": {
                    "deep": {"value": "test", "array": [1, 2, 3, 4, 5], "flags": {"a": True, "b": False, "c": None}}
                },
            },
        },
    },
}

OPENAI_TOOL_CALLS = {
    "tool_calls": [
        {
            "id": "call_abc123",
            "type": "function",
            "function": {"name": "search_database", "arguments": '{"query": "recent orders", "limit": 50}'},
        },
        {
            "id": "call_def456",
            "type": "function",
            "function": {"name": "analyze_data", "arguments": '{"data": [1,2,3,4,5], "method": "statistical"}'},
        },
    ]
}

TOOL_RESULT = {
    "tool_call_id": "call_abc123",
    "name": "search_database",
    "result": {
        "status": "success",
        "data": [
            {"id": 1, "name": "Order #001", "total": 150.50, "items": ["A", "B", "C"]},
            {"id": 2, "name": "Order #002", "total": 299.99, "items": ["X", "Y"]},
            {"id": 3, "name": "Order #003", "total": 75.25, "items": ["M", "N", "O", "P"]},
        ],
        "metadata": {"total_count": 50, "execution_time_ms": 45.3, "cached": False},
    },
    "error": None,
}

# Large batch of tool calls (simulating multi-agent scenario)
BATCH_TOOL_CALLS = {
    "batch": [
        {
            "id": f"call_{i}",
            "name": f"tool_{i % 10}",
            "arguments": {"param1": f"value_{i}", "param2": i * 10, "nested": {"data": list(range(10))}},
        }
        for i in range(100)
    ]
}


def benchmark_serialization(iterations=10000):
    """Benchmark JSON serialization (dumps)."""
    print("\n" + "=" * 80)
    print("JSON SERIALIZATION BENCHMARK (dumps)")
    print("=" * 80)
    print(f"Iterations: {iterations:,}")
    print(f"Using orjson: {fast_json.HAS_ORJSON}")

    test_cases = [
        ("Simple tool call", SIMPLE_TOOL_CALL),
        ("Complex tool call", COMPLEX_TOOL_CALL),
        ("OpenAI tool calls", OPENAI_TOOL_CALLS),
        ("Tool result", TOOL_RESULT),
        ("Batch (100 calls)", BATCH_TOOL_CALLS),
    ]

    total_fast = 0
    total_stdlib = 0

    for name, data in test_cases:
        # Benchmark fast_json (orjson or stdlib)
        start = time.perf_counter()
        for _ in range(iterations):
            fast_json.dumps(data)
        fast_time = time.perf_counter() - start
        total_fast += fast_time

        # Benchmark stdlib json for comparison
        start = time.perf_counter()
        for _ in range(iterations):
            stdlib_json.dumps(data)
        stdlib_time = time.perf_counter() - start
        total_stdlib += stdlib_time

        # Calculate speedup
        speedup = stdlib_time / fast_time if fast_time > 0 else 0

        print(f"\n  {name}:")
        print(f"    fast_json:   {fast_time:.4f}s ({iterations / fast_time:,.0f} ops/sec)")
        print(f"    stdlib json: {stdlib_time:.4f}s ({iterations / stdlib_time:,.0f} ops/sec)")
        print(f"    Speedup:     {speedup:.2f}x")

    # Overall summary
    overall_speedup = total_stdlib / total_fast if total_fast > 0 else 0
    print(f"\n  Overall serialization speedup: {overall_speedup:.2f}x")

    return overall_speedup


def benchmark_deserialization(iterations=10000):
    """Benchmark JSON deserialization (loads)."""
    print("\n" + "=" * 80)
    print("JSON DESERIALIZATION BENCHMARK (loads)")
    print("=" * 80)
    print(f"Iterations: {iterations:,}")

    test_cases = [
        ("Simple tool call", SIMPLE_TOOL_CALL),
        ("Complex tool call", COMPLEX_TOOL_CALL),
        ("OpenAI tool calls", OPENAI_TOOL_CALLS),
        ("Tool result", TOOL_RESULT),
        ("Batch (100 calls)", BATCH_TOOL_CALLS),
    ]

    total_fast = 0
    total_stdlib = 0

    for name, data in test_cases:
        # Pre-serialize the test data
        json_str = stdlib_json.dumps(data)

        # Benchmark fast_json (orjson or stdlib)
        start = time.perf_counter()
        for _ in range(iterations):
            fast_json.loads(json_str)
        fast_time = time.perf_counter() - start
        total_fast += fast_time

        # Benchmark stdlib json for comparison
        start = time.perf_counter()
        for _ in range(iterations):
            stdlib_json.loads(json_str)
        stdlib_time = time.perf_counter() - start
        total_stdlib += stdlib_time

        # Calculate speedup
        speedup = stdlib_time / fast_time if fast_time > 0 else 0

        print(f"\n  {name}:")
        print(f"    fast_json:   {fast_time:.4f}s ({iterations / fast_time:,.0f} ops/sec)")
        print(f"    stdlib json: {stdlib_time:.4f}s ({iterations / stdlib_time:,.0f} ops/sec)")
        print(f"    Speedup:     {speedup:.2f}x")

    # Overall summary
    overall_speedup = total_stdlib / total_fast if total_fast > 0 else 0
    print(f"\n  Overall deserialization speedup: {overall_speedup:.2f}x")

    return overall_speedup


def benchmark_round_trip(iterations=5000):
    """Benchmark full round-trip (dumps + loads)."""
    print("\n" + "=" * 80)
    print("JSON ROUND-TRIP BENCHMARK (dumps + loads)")
    print("=" * 80)
    print(f"Iterations: {iterations:,}")

    test_cases = [
        ("Simple tool call", SIMPLE_TOOL_CALL),
        ("Complex tool call", COMPLEX_TOOL_CALL),
        ("OpenAI tool calls", OPENAI_TOOL_CALLS),
        ("Tool result", TOOL_RESULT),
    ]

    total_fast = 0
    total_stdlib = 0

    for name, data in test_cases:
        # Benchmark fast_json (orjson or stdlib)
        start = time.perf_counter()
        for _ in range(iterations):
            json_str = fast_json.dumps(data)
            _ = fast_json.loads(json_str)
        fast_time = time.perf_counter() - start
        total_fast += fast_time

        # Benchmark stdlib json for comparison
        start = time.perf_counter()
        for _ in range(iterations):
            json_str = stdlib_json.dumps(data)
            _ = stdlib_json.loads(json_str)
        stdlib_time = time.perf_counter() - start
        total_stdlib += stdlib_time

        # Calculate speedup
        speedup = stdlib_time / fast_time if fast_time > 0 else 0

        print(f"\n  {name}:")
        print(f"    fast_json:   {fast_time:.4f}s ({iterations / fast_time:,.0f} ops/sec)")
        print(f"    stdlib json: {stdlib_time:.4f}s ({iterations / stdlib_time:,.0f} ops/sec)")
        print(f"    Speedup:     {speedup:.2f}x")

    # Overall summary
    overall_speedup = total_stdlib / total_fast if total_fast > 0 else 0
    print(f"\n  Overall round-trip speedup: {overall_speedup:.2f}x")

    return overall_speedup


def main():
    print("\n" + "=" * 80)
    print("CHUK-TOOL-PROCESSOR JSON PERFORMANCE BENCHMARK")
    print("=" * 80)

    # Run benchmarks
    serialize_speedup = benchmark_serialization(10000)
    deserialize_speedup = benchmark_deserialization(10000)
    roundtrip_speedup = benchmark_round_trip(5000)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Using orjson: {'YES' if fast_json.HAS_ORJSON else 'NO (using stdlib json)'}")
    print("\nSpeedup vs stdlib json:")
    print(f"  Serialization:   {serialize_speedup:.2f}x faster")
    print(f"  Deserialization: {deserialize_speedup:.2f}x faster")
    print(f"  Round-trip:      {roundtrip_speedup:.2f}x faster")

    if fast_json.HAS_ORJSON:
        print(f"\nOverall performance improvement: {roundtrip_speedup:.2f}x faster with orjson")
        print("This translates to 2-3x more tool call processing throughput!")
    else:
        print("\nInstall orjson for 2-3x faster JSON operations:")
        print("   pip install 'chuk-tool-processor[fast-json]'")
        print("   or: uv add --optional fast-json orjson")

    print("=" * 80)


if __name__ == "__main__":
    main()
