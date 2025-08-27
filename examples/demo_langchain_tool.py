#!/usr/bin/env python
# examples/demo_langchain_tool.py
"""
Demo: expose a LangChain `BaseTool` as an async-native chuk-tool.
"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

from langchain.tools.base import BaseTool

from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.registry import initialize, register_tool


# ----------------------------------------------------------------------
# 1.  A regular LangChain tool (sync + async implementations)
# ----------------------------------------------------------------------
class PalindromeTool(BaseTool):
    name: ClassVar[str] = "palindrome_tool"
    description: ClassVar[str] = "Return whether the given text is a palindrome."

    # sync entry-point used by BaseTool.run()
    def _run(self, tool_input: str, *args: Any, **kwargs: Any) -> dict:
        is_pal = tool_input.lower() == tool_input[::-1].lower()
        return {"text": tool_input, "palindrome": is_pal}

    # async entry-point used by BaseTool.arun()
    async def _arun(  # noqa: D401
        self,
        tool_input: str,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> dict:
        return self._run(tool_input)


# ----------------------------------------------------------------------
# 2.  Minimal async wrapper exposing `.execute()` for the executor
# ----------------------------------------------------------------------
@register_tool(name="palindrome_tool")
class PalindromeAdapter:
    """
    Thin adapter that forwards the call to the LangChain tool's
    async API and simply returns its result.
    """

    def __init__(self) -> None:
        # One tool instance is enough; LangChain tools are thread-safe.
        self._tool = PalindromeTool()

    async def execute(self, tool_input: str) -> dict:  # chuk-tool signature
        return await self._tool.arun(tool_input=tool_input)


# ----------------------------------------------------------------------
# 3.  Demo run
# ----------------------------------------------------------------------
async def main() -> None:
    # Initialise the default registry *and* make sure our adapter is loaded
    registry = await initialize()  # returns the same singleton each call

    # Create an executor bound to that registry
    executor = ToolExecutor(registry=registry)

    # Simulate an LLM-produced tool-call
    call = ToolCall(tool="palindrome_tool", arguments={"tool_input": "Madam"})

    # Execute
    (result,) = await executor.execute([call])

    # Show the outcome
    print("\n=== LangChain Tool Demo ===")
    if result.error:
        print("ERROR:", result.error)
    else:
        print("Tool :", result.tool)
        print("Data :", result.result)


if __name__ == "__main__":
    asyncio.run(main())
