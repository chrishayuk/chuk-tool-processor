#!/usr/bin/env python
"""
60-Second Hello Tool - The Simplest Possible Example

A single-file, copy-paste-and-run example that registers a tool,
parses OpenAI and Anthropic tool calls, executes, and prints results.

Run this:
    python hello_tool.py

Takes 60 seconds to understand, 3 minutes to master.
"""

import asyncio
import json
from chuk_tool_processor import ToolProcessor, initialize, register_tool


# --------------------------------------------------------------
# Step 1: Define a tool
# --------------------------------------------------------------
@register_tool(name="hello")
class HelloTool:
    """A simple tool that greets users."""

    async def execute(self, name: str) -> dict:
        """Execute the hello tool."""
        return {"greeting": f"Hello, {name}!"}


# --------------------------------------------------------------
# Step 2: Process tool calls from different LLM formats
# --------------------------------------------------------------
async def main():
    # Initialize the registry
    await initialize()

    # Use context manager for automatic cleanup
    async with ToolProcessor() as processor:
        print("=" * 60)
        print("60-Second Hello Tool Example")
        print("=" * 60)
        print()

        # -----------------------------------------------------------
        # Example 1: Anthropic XML format (Claude)
        # -----------------------------------------------------------
        print("1. Anthropic XML format:")
        print('   <tool name="hello" args=\'{"name": "World"}\'/>')
        print()

        xml_input = '<tool name="hello" args=\'{"name": "World"}\'/>'
        results = await processor.process(xml_input)

        print(f"   Result: {results[0].result}")
        print(f"   Duration: {results[0].duration:.3f}s")
        print()

        # -----------------------------------------------------------
        # Example 2: OpenAI tool_calls format (GPT-4)
        # -----------------------------------------------------------
        print("2. OpenAI tool_calls format:")
        openai_input = {
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "hello",
                        "arguments": '{"name": "OpenAI"}'
                    }
                }
            ]
        }
        print(f"   {json.dumps(openai_input, indent=2)}")
        print()

        results = await processor.process(json.dumps(openai_input))

        print(f"   Result: {results[0].result}")
        print(f"   Duration: {results[0].duration:.3f}s")
        print()

        # -----------------------------------------------------------
        # Example 3: Direct JSON format (raw API)
        # -----------------------------------------------------------
        print("3. Direct JSON format:")
        json_input = {
            "tool_calls": [
                {"tool": "hello", "arguments": {"name": "Developer"}}
            ]
        }
        print(f"   {json.dumps(json_input, indent=2)}")
        print()

        results = await processor.process(json.dumps(json_input))

        if results:
            print(f"   Result: {results[0].result}")
            print(f"   Duration: {results[0].duration:.3f}s")
        else:
            print("   No results")
        print()

        # -----------------------------------------------------------
        # Example 4: Error handling
        # -----------------------------------------------------------
        print("4. Error handling:")
        print('   <tool name="nonexistent" args=\'{}\'/>')
        print()

        error_input = '<tool name="nonexistent" args=\'{}\'/>'
        results = await processor.process(error_input)

        if results and results[0].error:
            print(f"   Error: {results[0].error}")
        elif not results:
            print("   No results (tool not found or parse error)")
        print()

        # -----------------------------------------------------------
        # Summary
        # -----------------------------------------------------------
        print("=" * 60)
        print("That's it! Three steps:")
        print("  1. Define a tool with @register_tool")
        print("  2. Call await processor.process(llm_output)")
        print("  3. Get structured results with .result, .error, .duration")
        print()
        print("Works with:")
        print("  - OpenAI tool_calls (GPT-4)")
        print("  - Anthropic XML tags (Claude)")
        print("  - Direct JSON (any LLM)")
        print()
        print("Production ready:")
        print("  - Automatic timeouts")
        print("  - Retry support")
        print("  - Caching")
        print("  - Rate limiting")
        print("  - Error handling")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
