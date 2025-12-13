# chuk_tool_processor/scheduling/policy.py
"""
SchedulerPolicy protocol definition.

This module defines the interface that all schedulers must implement.
The protocol is designed to be:
- Simple: one method, deterministic, no side effects
- Composable: cheap greedy or expensive solver-backed implementations
- Compatible: works with existing parallel execution and bulkheads
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from chuk_tool_processor.scheduling.types import (
        ExecutionPlan,
        SchedulingConstraints,
        ToolCallSpec,
    )


class SchedulerPolicy(Protocol):
    """
    Protocol for scheduling policies.

    A scheduler takes a set of tool calls with their constraints and
    produces an execution plan. The plan specifies:
    - Which calls to execute in which order (stages)
    - Per-call overrides (timeouts, retries)
    - Which calls to skip (infeasible or low priority)

    Implementations can be:
    - **Greedy**: Sort by priority/ETA, respect dependencies topologically
    - **Solver-backed**: Use CP-SAT to optimize for deadline/cost constraints
    - **Custom**: Any deterministic planning logic

    Example:
        >>> class MyScheduler:
        ...     def plan(self, calls, constraints, context=None):
        ...         # Simple: run everything in one stage
        ...         return ExecutionPlan(
        ...             stages=(tuple(c.call_id for c in calls),)
        ...         )
    """

    def plan(
        self,
        calls: Sequence[ToolCallSpec],
        constraints: SchedulingConstraints,
        context: Mapping[str, object] | None = None,
    ) -> ExecutionPlan:
        """
        Create an execution plan for the given calls and constraints.

        Args:
            calls: Tool calls to schedule
            constraints: Global constraints (deadline, cost, pool limits)
            context: Optional request-scoped context (tenant, user, etc.)

        Returns:
            An ExecutionPlan specifying stages, overrides, and skips
        """
        ...  # pragma: no cover
