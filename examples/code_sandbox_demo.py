#!/usr/bin/env python3
"""
Code Sandbox Demo - Tool-Processor Programmatic Execution

Demonstrates the tool-processor's built-in code execution sandbox that enables
programmatic tool orchestration for ANY LLM (not just those with built-in code
execution like Claude).

The sandbox:
- Executes Python code safely with registered tools
- Provides security controls and resource limits
- Works with any LLM that can generate Python code

Usage:
    uv run python examples/code_sandbox_demo.py
"""

import asyncio
import sys
import os

# Use local source
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chuk_tool_processor.execution.code_sandbox import CodeSandbox
from chuk_tool_processor.mcp.models import MCPServerConfig
from chuk_tool_processor.mcp.register_mcp_tools import register_mcp_tools
from chuk_tool_processor.mcp.stream_manager import StreamManager
from chuk_tool_processor.registry import reset_registry


async def demonstrate_code_sandbox():
    """Demonstrate tool-processor's programmatic execution via code sandbox."""
    print("=" * 80)
    print("CODE SANDBOX - TOOL-PROCESSOR PROGRAMMATIC EXECUTION")
    print("=" * 80)
    print()

    # Reset registry
    await reset_registry()

    # ========================================================================
    # STEP 1: Connect to Math MCP Server and Register Tools
    # ========================================================================
    print("STEP 1: Setup - Connect to Math Server")
    print("-" * 80)
    print()

    try:
        # Create math server config
        math_server = MCPServerConfig(
            name="math",
            command="uvx",
            args=["chuk-mcp-math-server"],
        )

        # Connect using StreamManager
        stream_manager = await StreamManager.create_with_stdio(
            servers=[math_server.to_dict()],
        )
        print("✅ Connected to chuk-mcp-math-server")
    except Exception as e:
        print(f"❌ Failed to start math server: {e}")
        print()
        print("Make sure chuk-mcp-math-server is installed:")
        print("  pip install chuk-mcp-math-server")
        return

    # Register tools (all active, no deferred loading for this demo)
    core_tools = ["add", "subtract", "multiply", "divide"]
    await register_mcp_tools(
        stream_manager=stream_manager,
        namespace="math",
        defer_loading=True,
        defer_all_except=core_tools,
    )

    print(f"✅ Registered {len(core_tools)} math tools")
    print()

    # ========================================================================
    # STEP 2: Create Code Sandbox
    # ========================================================================
    print("STEP 2: Create Code Sandbox")
    print("-" * 80)
    print()

    sandbox = CodeSandbox(timeout=30.0)
    print("✅ Code sandbox created with:")
    print("   • 30 second timeout")
    print("   • Safe Python builtins only")
    print("   • Access to registered tools")
    print()

    # ========================================================================
    # STEP 3: Execute Simple Loop
    # ========================================================================
    print("STEP 3: Execute Code with Loop")
    print("-" * 80)
    print()

    code1 = """
# Sum numbers using add tool in a loop
results = []
for i in range(1, 6):
    result = await add(a=str(i), b=str(i))
    value = result.content[0]['text']
    results.append(f"{i} + {i} = {value}")

return results
"""

    print("Code to execute:")
    print("```python")
    print(code1.strip())
    print("```")
    print()

    print("Executing...")
    result1 = await sandbox.execute(code1, namespace="math")

    print()
    print("Results:")
    for line in result1:
        print(f"  • {line}")
    print()

    # ========================================================================
    # STEP 4: Execute Conditional Logic
    # ========================================================================
    print("STEP 4: Execute Code with Conditionals")
    print("-" * 80)
    print()

    code2 = """
# Use conditionals with tool calls
results = []
numbers = [10, 20, 30, 40, 50]

for num in numbers:
    if num < 30:
        # Small numbers: add 100
        result = await add(a=str(num), b="100")
        op = "+100"
    else:
        # Large numbers: add 200
        result = await add(a=str(num), b="200")
        op = "+200"

    value = result.content[0]['text']
    results.append(f"{num} {op} = {value}")

return results
"""

    print("Code to execute:")
    print("```python")
    for line in code2.strip().split("\n")[:8]:
        print(line)
    print("  ...")
    print("```")
    print()

    print("Executing...")
    result2 = await sandbox.execute(code2, namespace="math")

    print()
    print("Results:")
    for line in result2:
        print(f"  • {line}")
    print()

    # ========================================================================
    # STEP 5: Complex Multi-Step Workflow
    # ========================================================================
    print("STEP 5: Complex Multi-Step Workflow")
    print("-" * 80)
    print()

    code3 = """
# Complex workflow chaining tool calls
steps = []

# Step 1: Add two numbers
step1 = await add(a="100", b="50")
result1 = step1.content[0]['text']
steps.append(f"Step 1: 100 + 50 = {result1}")

# Step 2: Add to previous result
step2 = await add(a=result1, b="30")
result2 = step2.content[0]['text']
steps.append(f"Step 2: {result1} + 30 = {result2}")

# Step 3: Add again
step3 = await add(a=result2, b="20")
result3 = step3.content[0]['text']
steps.append(f"Step 3: {result2} + 20 = {result3}")

# Step 4: Final addition
step4 = await add(a=result3, b="10")
result4 = step4.content[0]['text']
steps.append(f"Step 4: {result3} + 10 = {result4}")

return {
    "steps": steps,
    "final_result": result4
}
"""

    print("Code to execute:")
    print("```python")
    print("# Complex 4-step workflow")
    print("# Each step uses result from previous step")
    print("# Demonstrates chaining tool calls")
    print("```")
    print()

    print("Executing...")
    result3 = await sandbox.execute(code3, namespace="math")

    print()
    print("Workflow Results:")
    for step in result3["steps"]:
        print(f"  • {step}")
    print()
    print(f"Final Result: {result3['final_result']}")
    print()

    # ========================================================================
    # STEP 6: Benefits Summary
    # ========================================================================
    print("=" * 80)
    print("BENEFITS OF TOOL-PROCESSOR CODE EXECUTION")
    print("=" * 80)
    print()

    print("✅ Works with ANY LLM:")
    print("   • OpenAI GPT-4 (generate Python → execute in sandbox)")
    print("   • Anthropic Claude (generate Python → execute in sandbox)")
    print("   • Open source models (Llama, Mistral, etc.)")
    print("   • Any LLM that can generate Python code")
    print()

    print("✅ Security:")
    print("   • Sandboxed execution (restricted builtins)")
    print("   • Resource limits (timeout, memory)")
    print("   • Tool allowlist (only registered tools)")
    print("   • No file I/O or network access from code")
    print()

    print("✅ Performance:")
    print("   • All tool calls in single execution context")
    print("   • Zero token cost for control flow")
    print("   • Intermediate values stay in memory")
    print("   • Complex workflows execute efficiently")
    print()

    print("✅ Flexibility:")
    print("   • Full Python language (loops, conditionals, functions)")
    print("   • Multi-step workflows with data passing")
    print("   • Error handling and retries")
    print("   • Parallel tool execution (asyncio.gather)")
    print()

    print("=" * 80)
    print("DEMO COMPLETE")
    print("=" * 80)
    print()

    print("🎉 The tool-processor now provides programmatic execution for ANY LLM!")
    print("   LLM generates Python → Tool-processor executes safely")
    print()


async def main():
    """Main entry point."""
    try:
        await demonstrate_code_sandbox()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
