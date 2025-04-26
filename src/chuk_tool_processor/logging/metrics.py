# chuk_tool_processor/logging/metrics.py
from __future__ import annotations
from .context import get_logger

__all__ = ["metrics", "MetricsLogger"]


class MetricsLogger:
    def __init__(self):
        self.logger = get_logger("chuk_tool_processor.metrics")

    # ------------------------------------------------------------------
    def log_tool_execution(
        self,
        tool: str,
        success: bool,
        duration: float,
        *,
        error: str | None = None,
        cached: bool = False,
        attempts: int = 1,
    ):
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

    def log_parser_metric(
        self,
        parser: str,
        success: bool,
        duration: float,
        num_calls: int,
    ):
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


metrics = MetricsLogger()
