# chuk_tool_processor/scheduling/types.py
"""
Core types for the scheduling system.

These types define the data structures used by schedulers to plan
tool execution order, manage dependencies, and enforce constraints.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolMetadata(BaseModel):
    """
    Metadata for scheduling decisions.

    This information helps the scheduler make decisions about:
    - Which pool/bulkhead the tool belongs to
    - Estimated execution time for deadline planning
    - Cost for budget-aware scheduling
    - Priority for ordering decisions

    Attributes:
        pool: Pool/bulkhead name for concurrency grouping (e.g., "web", "db", "mcp.notion")
        weight: Weight for fair queuing (higher = more resources)
        est_ms: Estimated execution time in milliseconds
        cost: Cost in abstract units (credits, dollars, etc.)
        priority: Priority level (higher = sooner execution)
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pool: str = Field(
        default="default",
        description="Pool/bulkhead name for concurrency grouping",
    )
    weight: int = Field(
        default=1,
        ge=1,
        description="Weight for fair queuing (higher = more resources)",
    )
    est_ms: int | None = Field(
        default=None,
        ge=0,
        description="Estimated execution time in milliseconds",
    )
    cost: float | None = Field(
        default=None,
        ge=0,
        description="Cost in abstract units (credits, dollars, etc.)",
    )
    priority: int = Field(
        default=0,
        description="Priority level (higher = sooner execution)",
    )


class ToolCallSpec(BaseModel):
    """
    A tool call specification for scheduling.

    This extends the basic ToolCall with scheduling-specific metadata
    like dependencies, pool assignment, and timeout overrides.

    Attributes:
        call_id: Unique identifier for this call
        tool_name: Name of the tool to execute
        args: Arguments to pass to the tool
        metadata: Scheduling metadata (pool, priority, est_ms, etc.)
        depends_on: List of call_ids that must complete before this call
        timeout_ms: Optional per-call timeout override
        max_retries: Optional per-call retry limit override
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    call_id: str = Field(..., min_length=1, description="Unique identifier for this call")
    tool_name: str = Field(..., min_length=1, description="Name of the tool to execute")
    args: dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments to pass to the tool",
    )
    metadata: ToolMetadata = Field(
        default_factory=ToolMetadata,
        description="Scheduling metadata",
    )
    depends_on: tuple[str, ...] = Field(
        default=(),
        description="List of call_ids that must complete before this call",
    )
    timeout_ms: int | None = Field(
        default=None,
        ge=0,
        description="Optional per-call timeout override in milliseconds",
    )
    max_retries: int | None = Field(
        default=None,
        ge=0,
        description="Optional per-call retry limit override",
    )


class SchedulingConstraints(BaseModel):
    """
    Global constraints for scheduling.

    These constraints limit what the scheduler can do and help it
    make tradeoffs (e.g., skip low-priority calls if deadline is tight).

    Attributes:
        deadline_ms: Total wall-clock budget in milliseconds
        max_cost: Maximum total cost across all calls
        pool_limits: Per-pool concurrency limits (pool_name -> max_concurrent)
        now_ms: Current time in milliseconds (for testing/determinism)
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    deadline_ms: int | None = Field(
        default=None,
        ge=0,
        description="Total wall-clock budget in milliseconds",
    )
    max_cost: float | None = Field(
        default=None,
        ge=0,
        description="Maximum total cost across all calls",
    )
    pool_limits: dict[str, int] = Field(
        default_factory=dict,
        description="Per-pool concurrency limits (pool_name -> max_concurrent)",
    )
    now_ms: int = Field(
        default=0,
        ge=0,
        description="Current time in milliseconds (for testing/determinism)",
    )


class SkipReason(BaseModel):
    """Reason why a call was skipped."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    call_id: str = Field(..., description="The call that was skipped")
    reason: str = Field(..., description="Why it was skipped")
    detail: str | None = Field(default=None, description="Additional detail")


class ExecutionPlan(BaseModel):
    """
    The output of a scheduler: an execution plan.

    The plan specifies:
    - Stages: ordered batches of calls that can run concurrently
    - Per-call overrides: timeout/retry adjustments decided by the scheduler
    - Skip list: calls that should be skipped (infeasible or low priority)
    - Explainability: critical path, pool utilization, skip reasons

    Attributes:
        stages: List of stages, each containing call_ids that can run concurrently
        per_call_timeout_ms: Per-call timeout overrides (call_id -> timeout_ms)
        per_call_max_retries: Per-call retry overrides (call_id -> max_retries)
        skip: Call IDs to skip (deadline/cost infeasible or low priority)
        skip_reasons: Detailed reasons for each skipped call
        critical_path_ms: Estimated critical path duration in milliseconds
        estimated_total_ms: Estimated total execution time
        pool_utilization: Per-pool estimated utilization (pool -> concurrent calls)
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    stages: tuple[tuple[str, ...], ...] = Field(
        default=(),
        description="Ordered stages of call_ids that can run concurrently",
    )
    per_call_timeout_ms: dict[str, int] = Field(
        default_factory=dict,
        description="Per-call timeout overrides (call_id -> timeout_ms)",
    )
    per_call_max_retries: dict[str, int] = Field(
        default_factory=dict,
        description="Per-call retry overrides (call_id -> max_retries)",
    )
    skip: tuple[str, ...] = Field(
        default=(),
        description="Call IDs to skip (deadline/cost infeasible or low priority)",
    )
    # Explainability fields
    skip_reasons: tuple[SkipReason, ...] = Field(
        default=(),
        description="Detailed reasons for each skipped call",
    )
    critical_path_ms: int | None = Field(
        default=None,
        ge=0,
        description="Estimated critical path duration in milliseconds",
    )
    estimated_total_ms: int | None = Field(
        default=None,
        ge=0,
        description="Estimated total execution time in milliseconds",
    )
    pool_utilization: dict[str, int] = Field(
        default_factory=dict,
        description="Per-pool max concurrent calls in plan",
    )

    @property
    def all_scheduled_calls(self) -> set[str]:
        """Get all call IDs that are scheduled (not skipped)."""
        return {call_id for stage in self.stages for call_id in stage}

    @property
    def total_stages(self) -> int:
        """Get the total number of stages."""
        return len(self.stages)
