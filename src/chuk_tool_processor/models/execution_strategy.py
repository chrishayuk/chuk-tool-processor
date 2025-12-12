# chuk_tool_processor/models/execution_strategy.py
"""
Abstract base class for tool execution strategies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable

from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult


class ExecutionStrategy(ABC):
    """
    Strategy interface for executing ToolCall objects.

    All execution strategies must implement at least the run method,
    and optionally stream_run for streaming support.

    PARALLEL EXECUTION NOTE:
    Results are returned in COMPLETION ORDER, not submission order.
    This allows faster tools to return immediately without waiting for slower ones.
    Use the ToolResult.tool attribute to match results back to their original calls.
    """

    @abstractmethod
    async def run(self, calls: list[ToolCall], timeout: float | None = None) -> list[ToolResult]:
        """
        Execute a list of tool calls and return their results.

        Args:
            calls: List of ToolCall objects to execute
            timeout: Optional timeout in seconds for each call

        Returns:
            List of ToolResult objects in completion order (not submission order).
            Use ToolResult.tool to match results back to their original calls.
        """
        pass

    async def stream_run(
        self,
        calls: list[ToolCall],
        timeout: float | None = None,
        on_tool_start: Callable[[ToolCall], Awaitable[None]] | None = None,  # noqa: ARG002
    ) -> AsyncIterator[ToolResult]:
        """
        Execute tool calls and yield results as they become available.

        Default implementation executes all calls with run() and yields the results.
        Subclasses can override for true streaming behavior.

        Args:
            calls: List of ToolCall objects to execute
            timeout: Optional timeout in seconds for each call
            on_tool_start: Optional callback invoked when each tool starts execution.
                          Useful for emitting start events before results arrive.

        Yields:
            ToolResult objects as they become available (in completion order)
        """
        # Default implementation ignores on_tool_start since we batch execute
        # Subclasses with true streaming can use the callback
        results = await self.run(calls, timeout=timeout)
        for result in results:
            yield result

    @property
    def supports_streaming(self) -> bool:
        """
        Check if this strategy supports true streaming.

        Default implementation returns False. Streaming-capable strategies
        should override this to return True.
        """
        return False
