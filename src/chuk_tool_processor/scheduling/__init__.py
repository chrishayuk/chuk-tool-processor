# chuk_tool_processor/scheduling/__init__.py
"""
Scheduling module for tool execution planning.

This module provides:
- SchedulerPolicy protocol for pluggable scheduling strategies
- GreedyDagScheduler for deadline-aware DAG scheduling
- Types for tool metadata, constraints, and execution plans

Example:
    >>> from chuk_tool_processor.scheduling import (
    ...     GreedyDagScheduler,
    ...     ToolCallSpec,
    ...     SchedulingConstraints,
    ... )
    >>>
    >>> scheduler = GreedyDagScheduler()
    >>> calls = [
    ...     ToolCallSpec(call_id="1", tool_name="fetch", metadata=ToolMetadata(pool="web")),
    ...     ToolCallSpec(call_id="2", tool_name="transform", depends_on=["1"]),
    ...     ToolCallSpec(call_id="3", tool_name="store", depends_on=["2"]),
    ... ]
    >>> constraints = SchedulingConstraints(deadline_ms=5000, pool_limits={"web": 2})
    >>> plan = scheduler.plan(calls, constraints)
"""

from chuk_tool_processor.scheduling.greedy_dag import GreedyDagScheduler
from chuk_tool_processor.scheduling.policy import SchedulerPolicy
from chuk_tool_processor.scheduling.types import (
    ExecutionPlan,
    SchedulingConstraints,
    SkipReason,
    ToolCallSpec,
    ToolMetadata,
)

__all__ = [
    # Types
    "ToolMetadata",
    "ToolCallSpec",
    "SchedulingConstraints",
    "ExecutionPlan",
    "SkipReason",
    # Protocol
    "SchedulerPolicy",
    # Implementations
    "GreedyDagScheduler",
]
