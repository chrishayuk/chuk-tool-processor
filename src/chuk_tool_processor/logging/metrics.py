# chuk_tool_processor/logging/metrics.py
"""
Metrics logging for tool execution.
"""

from __future__ import annotations

# Import directly from context to avoid circular imports
from .context import get_logger

__all__ = ["metrics", "MetricsLogger"]


class MetricsLogger:
    """
    Logger for collecting and reporting metrics about tool execution.

    Provides methods to log tool execution metrics and parser metrics
    in a structured format.
    """

    def __init__(self):
        """Initialize with logger."""
        self.logger = get_logger("chuk_tool_processor.metrics")

    # ------------------------------------------------------------------
    async def log_tool_execution(
        self,
        tool: str,
        success: bool,
        duration: float,
        *,
        error: str | None = None,
        cached: bool = False,
        attempts: int = 1,
    ) -> None:
        """
        Log metrics for a tool execution.

        Args:
            tool: Name of the tool
            success: Whether execution was successful
            duration: Execution duration in seconds
            error: Optional error message if execution failed
            cached: Whether the result was retrieved from cache
            attempts: Number of execution attempts
        """
        self.logger.info(
            f"Tool execution metric: {tool}",
            extra={
                "context": {
                    "metric_type": "tool_execution",
                    "tool": tool,
                    "success": success,
                    "duration": duration,
                    "error": error,
                    "cached": cached,
                    "attempts": attempts,
                }
            },
        )

    async def log_parser_metric(
        self,
        parser: str,
        success: bool,
        duration: float,
        num_calls: int,
    ) -> None:
        """
        Log metrics for a parser.

        Args:
            parser: Name of the parser
            success: Whether parsing was successful
            duration: Parsing duration in seconds
            num_calls: Number of tool calls parsed
        """
        self.logger.info(
            f"Parser metric: {parser}",
            extra={
                "context": {
                    "metric_type": "parser",
                    "parser": parser,
                    "success": success,
                    "duration": duration,
                    "num_calls": num_calls,
                }
            },
        )

    async def log_registry_metric(
        self,
        operation: str,
        success: bool,
        duration: float,
        tool: str | None = None,
        namespace: str | None = None,
    ) -> None:
        """
        Log metrics for registry operations.

        Args:
            operation: Type of registry operation
            success: Whether operation was successful
            duration: Operation duration in seconds
            tool: Optional tool name
            namespace: Optional namespace
        """
        self.logger.info(
            f"Registry metric: {operation}",
            extra={
                "context": {
                    "metric_type": "registry",
                    "operation": operation,
                    "success": success,
                    "duration": duration,
                    "tool": tool,
                    "namespace": namespace,
                }
            },
        )


# Create global instance
metrics = MetricsLogger()
