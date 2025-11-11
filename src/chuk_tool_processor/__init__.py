"""
CHUK Tool Processor - Async-native framework for processing LLM tool calls.

This package provides a production-ready framework for:
- Processing tool calls from various LLM output formats
- Executing tools with timeouts, retries, and rate limiting
- Connecting to remote MCP servers
- Caching results and circuit breaking

Quick Start:
    >>> import asyncio
    >>> from chuk_tool_processor import ToolProcessor
    >>>
    >>> async def main():
    ...     async with ToolProcessor() as processor:
    ...         llm_output = '<tool name="calculator" args=\'{"a": 5, "b": 3}\'/>'
    ...         results = await processor.process(llm_output)
    ...         print(results[0].result)
    >>>
    >>> asyncio.run(main())
"""

from typing import TYPE_CHECKING

# Version
__version__ = "0.9.7"

# Core processor
from chuk_tool_processor.core.processor import ToolProcessor

# Execution strategies
from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.execution.strategies.subprocess_strategy import SubprocessStrategy
from chuk_tool_processor.execution.strategies.subprocess_strategy import SubprocessStrategy as IsolatedStrategy

# MCP setup helpers
from chuk_tool_processor.mcp import (
    setup_mcp_http_streamable,
    setup_mcp_sse,
    setup_mcp_stdio,
)

# Stream manager for advanced MCP usage
from chuk_tool_processor.mcp.stream_manager import StreamManager

# Models (commonly used)
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult

# Registry functions and types
from chuk_tool_processor.registry import (
    ToolInfo,
    ToolRegistryProvider,
    get_default_registry,
    initialize,
)
from chuk_tool_processor.registry.auto_register import register_fn_tool

# Decorators for registering tools
from chuk_tool_processor.registry.decorators import register_tool, tool

# Type checking imports (not available at runtime)
if TYPE_CHECKING:
    # Advanced models for type hints
    # Execution strategies
    from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
    from chuk_tool_processor.execution.strategies.subprocess_strategy import SubprocessStrategy

    # Retry config
    from chuk_tool_processor.execution.wrappers.retry import RetryConfig
    from chuk_tool_processor.models.streaming_tool import StreamingTool
    from chuk_tool_processor.models.tool_spec import ToolSpec
    from chuk_tool_processor.models.validated_tool import ValidatedTool

    # Registry interface
    from chuk_tool_processor.registry.interface import ToolRegistryInterface

# Public API
__all__ = [
    # Version
    "__version__",
    # Core classes
    "ToolProcessor",
    "StreamManager",
    # Models
    "ToolCall",
    "ToolResult",
    # Registry
    "ToolInfo",
    "initialize",
    "get_default_registry",
    "ToolRegistryProvider",
    # Decorators
    "register_tool",
    "tool",
    "register_fn_tool",
    # Execution strategies
    "InProcessStrategy",
    "IsolatedStrategy",
    "SubprocessStrategy",
    # MCP setup
    "setup_mcp_stdio",
    "setup_mcp_sse",
    "setup_mcp_http_streamable",
]

# Type checking exports (documentation only)
if TYPE_CHECKING:
    __all__ += [
        "ValidatedTool",
        "StreamingTool",
        "ToolSpec",
        "InProcessStrategy",
        "SubprocessStrategy",
        "ToolRegistryInterface",
        "RetryConfig",
    ]
