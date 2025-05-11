# examples/execution_strategies_custom_demo.py
#!/usr/bin/env python
"""
Example: a *toy* execution strategy that just upper-cases the tool name
and returns immediately - no real work, but shows the plumbing.
"""

import asyncio
import random
from typing import List, Optional

from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.plugins.discovery import plugin_registry
from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.registry import initialize        # default in-memory registry


# ---------------------------------------------------------------------
# Strategy definition
# ---------------------------------------------------------------------
class ShoutStrategy(ExecutionStrategy):
    """Returns the tool-name capitalised after a small random delay."""

    async def run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
    ) -> List[ToolResult]:
        async def _one(call: ToolCall) -> ToolResult:
            await asyncio.sleep(random.uniform(0.05, 0.2))
            return ToolResult(tool=call.tool, result=call.tool.upper())

        return await asyncio.gather(*(_one(c) for c in calls))

    # opt-in streaming
    @property
    def supports_streaming(self) -> bool:
        return True

    async def stream_run(self, calls, timeout=None):
        for c in calls:
            yield ToolResult(tool=c.tool, result=c.tool.upper())
            await asyncio.sleep(0.05)


# Register it so discovery can find it later
plugin_registry.register_plugin("execution_strategy", "ShoutStrategy", ShoutStrategy)


# ---------------------------------------------------------------------
# Try it out
# ---------------------------------------------------------------------
async def main() -> None:
    registry = await initialize()          # we don’t need real tools for this demo
    calls = [ToolCall(tool="ping"), ToolCall(tool="echo")]
    executor = ToolExecutor(registry=registry, strategy=ShoutStrategy())

    res = await executor.execute(calls)
    print("=== run() → list ===")
    for r in res:
        print(r)

    print("\n=== stream_execute() ===")
    async for r in executor.stream_execute(calls):
        print(r)


if __name__ == "__main__":
    asyncio.run(main())
