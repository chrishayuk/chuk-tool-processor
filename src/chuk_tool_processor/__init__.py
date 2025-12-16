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

# Core processor and context
# Configuration
from chuk_tool_processor.config import (
    BackendType,
    ProcessorConfig,
    RegistryConfig,
    ResilienceBackend,
    create_executor,
)
from chuk_tool_processor.core.context import (
    ContextHeader,
    ContextKey,
    ExecutionContext,
    execution_scope,
    get_current_context,
    set_current_context,
)
from chuk_tool_processor.core.processor import ToolProcessor

# Discovery (tool search and dynamic providers)
from chuk_tool_processor.discovery import (
    BaseDynamicToolProvider,
    DynamicToolName,
    SearchableTool,
    SearchResult,
    SessionToolStats,
    ToolSearchEngine,
    find_tool_by_alias,
    find_tool_exact,
    get_search_engine,
    search_tools,
)

# Execution strategies and bulkhead
from chuk_tool_processor.execution.bulkhead import (
    Bulkhead,
    BulkheadConfig,
    BulkheadFullError,
    BulkheadLimitType,
    BulkheadStats,
)
from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.execution.strategies.subprocess_strategy import SubprocessStrategy
from chuk_tool_processor.execution.strategies.subprocess_strategy import SubprocessStrategy as IsolatedStrategy

# Guards
from chuk_tool_processor.guards import (
    BaseGuard,
    BudgetGuard,
    BudgetGuardConfig,
    BudgetState,
    BudgetStatus,
    ConcurrencyConfig,
    ConcurrencyGuard,
    ConcurrencyLimitExceeded,
    ConcurrencyState,
    DegradeAction,
    EnforcementLevel,
    Environment,
    ErrorClass,
    ExecutionMode,
    Guard,
    GuardChain,
    GuardChainResult,
    GuardResult,
    GuardVerdict,
    NetworkPolicyConfig,
    NetworkPolicyGuard,
    NetworkViolation,
    NetworkViolationType,
    OutputSizeConfig,
    OutputSizeGuard,
    PerToolGuard,
    PerToolGuardConfig,
    PlanShapeConfig,
    PlanShapeGuard,
    PlanShapeState,
    PlanShapeViolation,
    PlanShapeViolationType,
    PreconditionGuard,
    PreconditionGuardConfig,
    ProvenanceConfig,
    ProvenanceGuard,
    ProvenanceRecord,
    RedactMode,
    RetrySafetyConfig,
    RetrySafetyGuard,
    RetryState,
    RunawayGuard,
    RunawayGuardConfig,
    SchemaStrictnessConfig,
    SchemaStrictnessGuard,
    SchemaValidationResult,
    SchemaViolation,
    SchemaViolationType,
    SensitiveDataConfig,
    SensitiveDataGuard,
    SensitiveDataType,
    SensitiveMatch,
    SideEffectClass,
    SideEffectConfig,
    SideEffectGuard,
    SizeViolation,
    SizeViolationType,
    TimeoutBudgetConfig,
    TimeoutBudgetGuard,
    TimeoutBudgetState,
    ToolClassification,
    TruncatedResult,
    TruncationMode,
    UnresolvedReferenceGuard,
    UnresolvedReferenceGuardConfig,
)

# MCP setup helpers
from chuk_tool_processor.mcp import (
    setup_mcp_http_streamable,
    setup_mcp_sse,
    setup_mcp_stdio,
)

# Stream manager for advanced MCP usage
from chuk_tool_processor.mcp.stream_manager import StreamManager

# Models (commonly used)
from chuk_tool_processor.models.return_order import ReturnOrder
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult

# Registry functions and types
from chuk_tool_processor.registry import (
    ToolInfo,
    ToolRegistryProvider,
    create_registry,
    get_default_registry,
    initialize,
)
from chuk_tool_processor.registry.auto_register import register_fn_tool

# Decorators for registering tools
from chuk_tool_processor.registry.decorators import register_tool, tool

# Scheduling
from chuk_tool_processor.scheduling import (
    ExecutionPlan,
    GreedyDagScheduler,
    SchedulerPolicy,
    SchedulingConstraints,
    ToolCallSpec,
    ToolMetadata,
)

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
    # ExecutionContext
    "ExecutionContext",
    "ContextHeader",
    "ContextKey",
    "execution_scope",
    "get_current_context",
    "set_current_context",
    # Bulkhead
    "Bulkhead",
    "BulkheadConfig",
    "BulkheadFullError",
    "BulkheadLimitType",
    "BulkheadStats",
    # Models
    "ToolCall",
    "ToolResult",
    "ReturnOrder",
    # Scheduling
    "ToolMetadata",
    "ToolCallSpec",
    "SchedulingConstraints",
    "ExecutionPlan",
    "SchedulerPolicy",
    "GreedyDagScheduler",
    # Registry
    "ToolInfo",
    "initialize",
    "get_default_registry",
    "create_registry",
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
    # Configuration
    "BackendType",
    "ProcessorConfig",
    "RegistryConfig",
    "ResilienceBackend",
    "create_executor",
    # Guards - Base
    "BaseGuard",
    "Guard",
    "GuardResult",
    "GuardVerdict",
    "EnforcementLevel",
    "ToolClassification",
    # Guards - Chain
    "GuardChain",
    "GuardChainResult",
    # Guards - Original
    "BudgetGuard",
    "BudgetGuardConfig",
    "BudgetState",
    "PerToolGuard",
    "PerToolGuardConfig",
    "PreconditionGuard",
    "PreconditionGuardConfig",
    "RunawayGuard",
    "RunawayGuardConfig",
    "UnresolvedReferenceGuard",
    "UnresolvedReferenceGuardConfig",
    # Guards - Schema Strictness
    "SchemaStrictnessGuard",
    "SchemaStrictnessConfig",
    "SchemaValidationResult",
    "SchemaViolation",
    "SchemaViolationType",
    # Guards - Output Size
    "OutputSizeGuard",
    "OutputSizeConfig",
    "SizeViolation",
    "SizeViolationType",
    "TruncatedResult",
    "TruncationMode",
    # Guards - Sensitive Data
    "SensitiveDataGuard",
    "SensitiveDataConfig",
    "SensitiveDataType",
    "SensitiveMatch",
    "RedactMode",
    # Guards - Concurrency
    "ConcurrencyGuard",
    "ConcurrencyConfig",
    "ConcurrencyState",
    "ConcurrencyLimitExceeded",
    # Guards - Network Policy
    "NetworkPolicyGuard",
    "NetworkPolicyConfig",
    "NetworkViolation",
    "NetworkViolationType",
    # Guards - Side Effect
    "SideEffectGuard",
    "SideEffectConfig",
    "SideEffectClass",
    "ExecutionMode",
    "Environment",
    # Guards - Timeout Budget
    "TimeoutBudgetGuard",
    "TimeoutBudgetConfig",
    "TimeoutBudgetState",
    "BudgetStatus",
    "DegradeAction",
    # Guards - Retry Safety
    "RetrySafetyGuard",
    "RetrySafetyConfig",
    "RetryState",
    "ErrorClass",
    # Guards - Provenance
    "ProvenanceGuard",
    "ProvenanceConfig",
    "ProvenanceRecord",
    # Guards - Plan Shape
    "PlanShapeGuard",
    "PlanShapeConfig",
    "PlanShapeState",
    "PlanShapeViolation",
    "PlanShapeViolationType",
    # Discovery
    "BaseDynamicToolProvider",
    "DynamicToolName",
    "ToolSearchEngine",
    "SearchResult",
    "SearchableTool",
    "SessionToolStats",
    "get_search_engine",
    "search_tools",
    "find_tool_exact",
    "find_tool_by_alias",
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
