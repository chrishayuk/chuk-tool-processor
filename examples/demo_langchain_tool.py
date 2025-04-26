# examples/demo_langchain_tool.py
"""
Demo: register a LangChain `BaseTool` with chuk-tool-processor and invoke it.
"""

from __future__ import annotations
import asyncio
from typing import ClassVar, Any

from langchain.tools.base import BaseTool
from chuk_tool_processor.registry.auto_register import register_langchain_tool
from chuk_tool_processor.core.processor import ToolProcessor
from chuk_tool_processor.models.tool_call import ToolCall


# ── LangChain tool definition ───────────────────────────────────────────────
class PalindromeTool(BaseTool):
    # pydantic requires concrete type annotations here
    name: ClassVar[str] = "palindrome_tool"
    description: ClassVar[str] = (
        "Return whether the given text is a palindrome."
    )

    # synchronous implementation (BaseTool will call this from .run/.arun)
    def _run(self, tool_input: str, *args: Any, **kwargs: Any) -> dict:
        is_pal = tool_input.lower() == tool_input[::-1].lower()
        return {"text": tool_input, "palindrome": is_pal}

    # asynchronous implementation (optional but nice to have)
    async def _arun(
        self, tool_input: str, run_manager: Any | None = None, **kwargs: Any
    ) -> dict:  # noqa: D401
        # Just delegate to the sync version for this demo
        return self._run(tool_input)


# ── register with the global registry ───────────────────────────────────────
register_langchain_tool(PalindromeTool())


# ── quick test run ──────────────────────────────────────────────────────────
async def main() -> None:
    proc = ToolProcessor(enable_caching=False)

    # Pretend the LLM called the tool with {"tool_input": "Madam"}
    call = ToolCall(tool="palindrome_tool", arguments={"tool_input": "Madam"})
    [result] = await proc.executor.execute([call])

    print("Tool results:")
    print("·", result.tool, result.result)


if __name__ == "__main__":
    asyncio.run(main())
