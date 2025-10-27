#!/usr/bin/env python
"""
Streaming Tool Calls Demo

Demonstrates handling partial tool call lists arriving mid-stream from an LLM.
This is useful when the LLM streams its response token-by-token and you want
to start executing tools as soon as they're complete, rather than waiting for
the entire response.

Key scenarios:
1. Partial tool calls in streaming responses
2. Processing complete tools while others are still arriving
3. Handling incomplete/malformed partial calls

Run this:
    python examples/streaming_tool_calls_demo.py
"""

import asyncio
import json
from chuk_tool_processor.core.processor import ToolProcessor
from chuk_tool_processor.registry import initialize, register_tool


# --------------------------------------------------------------
# Define some example tools
# --------------------------------------------------------------
@register_tool(name="calculator")
class CalculatorTool:
    """A simple calculator tool."""

    async def execute(self, operation: str, a: float, b: float) -> dict:
        """Execute a calculation."""
        ops = {
            "add": a + b,
            "subtract": a - b,
            "multiply": a * b,
            "divide": a / b if b != 0 else None,
        }
        return {"result": ops.get(operation)}


@register_tool(name="weather")
class WeatherTool:
    """A simple weather tool."""

    async def execute(self, location: str) -> dict:
        """Get weather for a location."""
        # Simulate API call
        await asyncio.sleep(0.1)
        return {"temperature": 72, "conditions": "sunny", "location": location}


@register_tool(name="database")
class DatabaseTool:
    """A simple database query tool."""

    async def execute(self, query: str) -> dict:
        """Execute a database query."""
        # Simulate query
        await asyncio.sleep(0.2)
        return {"rows": 42, "query": query}


# --------------------------------------------------------------
# Simulate streaming LLM responses
# --------------------------------------------------------------
async def simulate_streaming_llm():
    """
    Simulate an LLM streaming tool calls token-by-token.

    In a real scenario, this would be chunks from OpenAI's streaming API
    or Anthropic's streaming API.
    """
    # Complete response we're simulating
    complete_response = {
        "tool_calls": [
            {
                "tool": "calculator",
                "arguments": {"operation": "add", "a": 10, "b": 5}
            },
            {
                "tool": "weather",
                "arguments": {"location": "San Francisco"}
            },
            {
                "tool": "database",
                "arguments": {"query": "SELECT COUNT(*) FROM users"}
            }
        ]
    }

    # Simulate streaming by yielding partial JSON strings
    json_str = json.dumps(complete_response)

    # Stream in chunks (simulating token-by-token arrival)
    chunk_size = 20
    for i in range(0, len(json_str), chunk_size):
        chunk = json_str[i:i + chunk_size]
        yield chunk
        await asyncio.sleep(0.1)  # Simulate network delay


# --------------------------------------------------------------
# Parse partial tool calls
# --------------------------------------------------------------
def parse_partial_tool_calls(accumulated_text: str) -> list[dict] | None:
    """
    Try to parse accumulated text as JSON tool calls.

    Returns:
        - List of tool calls if parseable
        - None if not yet valid JSON
    """
    try:
        data = json.loads(accumulated_text)
        if isinstance(data, dict) and "tool_calls" in data:
            return data["tool_calls"]
        return None
    except json.JSONDecodeError:
        # Not yet valid JSON - keep accumulating
        return None


# --------------------------------------------------------------
# Main demo
# --------------------------------------------------------------
async def main():
    print("=" * 70)
    print("Streaming Tool Calls Demo")
    print("=" * 70)
    print()

    await initialize()
    processor = ToolProcessor()

    # Track state
    accumulated_text = ""
    processed_tool_indices = set()

    print("Scenario 1: Processing tool calls as they arrive in stream")
    print("-" * 70)
    print()

    async for chunk in simulate_streaming_llm():
        accumulated_text += chunk
        print(f"Received chunk: {chunk}")

        # Try to parse what we have so far
        tool_calls = parse_partial_tool_calls(accumulated_text)

        if tool_calls:
            print(f"  ✓ Parsed {len(tool_calls)} tool calls so far")

            # Process any complete tool calls we haven't processed yet
            for idx, tool_call in enumerate(tool_calls):
                if idx not in processed_tool_indices:
                    # Check if this tool call is complete
                    if all(k in tool_call for k in ["tool", "arguments"]):
                        print(f"  → Processing tool #{idx + 1}: {tool_call['tool']}")

                        # Convert to processor format and execute
                        input_data = {"tool_calls": [tool_call]}
                        results = await processor.process(json.dumps(input_data))

                        if results and not results[0].error:
                            print(f"    ✓ Result: {results[0].result}")
                            processed_tool_indices.add(idx)
                        elif results:
                            print(f"    ✗ Error: {results[0].error}")
        else:
            print("  ... (accumulating, not yet valid JSON)")

        print()

    print("=" * 70)
    print(f"Stream complete! Processed {len(processed_tool_indices)} tools")
    print("=" * 70)
    print()

    # --------------------------------------------------------------
    # Scenario 2: Handle OpenAI streaming format
    # --------------------------------------------------------------
    print("Scenario 2: OpenAI streaming format (delta chunks)")
    print("-" * 70)
    print()

    # OpenAI streams deltas like this
    openai_stream = [
        {"tool_calls": [{"index": 0, "function": {"name": "cal"}}]},
        {"tool_calls": [{"index": 0, "function": {"name": "culator"}}]},
        {"tool_calls": [{"index": 0, "function": {"arguments": '{"operation"'}}]},
        {"tool_calls": [{"index": 0, "function": {"arguments": ': "multiply", '}}]},
        {"tool_calls": [{"index": 0, "function": {"arguments": '"a": 7, "b": 6}'}}]},
    ]

    # Accumulate deltas
    tool_calls_state = {}

    for delta in openai_stream:
        print(f"Received delta: {delta}")

        for call_delta in delta.get("tool_calls", []):
            idx = call_delta.get("index", 0)

            if idx not in tool_calls_state:
                tool_calls_state[idx] = {"name": "", "arguments": ""}

            # Accumulate name
            if "function" in call_delta and "name" in call_delta["function"]:
                tool_calls_state[idx]["name"] += call_delta["function"]["name"]

            # Accumulate arguments
            if "function" in call_delta and "arguments" in call_delta["function"]:
                tool_calls_state[idx]["arguments"] += call_delta["function"]["arguments"]

        print(f"  State: {tool_calls_state}")
        print()

    # Process complete tool call
    print("Processing accumulated tool call:")
    complete_call = tool_calls_state[0]

    try:
        args = json.loads(complete_call["arguments"])
        input_data = {
            "tool_calls": [
                {"tool": complete_call["name"], "arguments": args}
            ]
        }

        results = await processor.process(json.dumps(input_data))

        if results and not results[0].error:
            print(f"  ✓ {complete_call['name']}: {results[0].result}")
        elif results:
            print(f"  ✗ Error: {results[0].error}")
    except json.JSONDecodeError:
        print(f"  ✗ Invalid arguments JSON: {complete_call['arguments']}")

    print()

    # --------------------------------------------------------------
    # Scenario 3: Handle Anthropic streaming XML
    # --------------------------------------------------------------
    print("Scenario 3: Anthropic streaming XML format")
    print("-" * 70)
    print()

    # Anthropic streams XML incrementally
    anthropic_stream = [
        '<tool name="weather',
        '" args=\'{"loc',
        'ation": "New',
        ' York"}\'/>',
    ]

    accumulated_xml = ""

    for chunk in anthropic_stream:
        accumulated_xml += chunk
        print(f"Received chunk: {chunk}")
        print(f"  Accumulated: {accumulated_xml}")

        # Try to process if we have a complete tag
        if accumulated_xml.endswith("/>"):
            print("  ✓ Complete XML tag detected")
            results = await processor.process(accumulated_xml)

            if results and not results[0].error:
                print(f"  ✓ Result: {results[0].result}")
            elif results:
                print(f"  ✗ Error: {results[0].error}")
        else:
            print("  ... (incomplete XML, waiting for more)")

        print()

    # --------------------------------------------------------------
    # Summary
    # --------------------------------------------------------------
    print("=" * 70)
    print("Key Takeaways:")
    print("=" * 70)
    print()
    print("1. Accumulate stream chunks into buffer")
    print("2. Try parsing after each chunk (fails gracefully if incomplete)")
    print("3. Process complete tool calls immediately (don't wait for full response)")
    print("4. Track which tools you've processed to avoid duplicates")
    print("5. Different formats need different accumulation strategies:")
    print("   - JSON: Parse full object")
    print("   - OpenAI deltas: Accumulate name + arguments separately")
    print("   - Anthropic XML: Wait for closing tag")
    print()
    print("Benefits:")
    print("  ✓ Lower latency (start executing tools ASAP)")
    print("  ✓ Better UX (show progress as tools complete)")
    print("  ✓ Parallel execution (tools run concurrently)")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
