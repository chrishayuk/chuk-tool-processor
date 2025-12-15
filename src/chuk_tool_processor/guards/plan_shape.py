# chuk_tool_processor/guards/plan_shape.py
"""Plan shape guard for detecting pathological execution patterns.

Guards against overly long chains, excessive unique tools, and fan-out explosions.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from chuk_tool_processor.guards.base import BaseGuard, GuardResult
from chuk_tool_processor.guards.models import EnforcementLevel


class PlanShapeViolationType(str, Enum):
    """Types of plan shape violations."""

    CHAIN_TOO_LONG = "chain_too_long"
    TOO_MANY_UNIQUE_TOOLS = "too_many_unique_tools"
    FAN_OUT_TOO_LARGE = "fan_out_too_large"
    FAN_OUT_FAN_IN_DETECTED = "fan_out_fan_in_detected"
    BATCH_TOO_LARGE = "batch_too_large"


class PlanShapeViolation(BaseModel):
    """A plan shape violation."""

    violation_type: PlanShapeViolationType
    limit: int
    actual: int
    detail: str = ""


class PlanShapeState(BaseModel):
    """Current execution state for tracking."""

    chain_depth: int = 0
    tools_seen: set[str] = Field(default_factory=set)
    current_fan_out: int = 0
    max_fan_out_seen: int = 0
    total_calls: int = 0


class PlanShapeConfig(BaseModel):
    """Configuration for PlanShapeGuard."""

    max_chain_length: int = Field(
        default=20,
        description="Maximum sequential tool calls in a chain",
    )
    max_unique_tools: int = Field(
        default=15,
        description="Maximum unique tools per run",
    )
    max_fan_out: int = Field(
        default=100,
        description="Maximum parallel calls from single point",
    )
    detect_fan_out_fan_in: bool = Field(
        default=True,
        description="Detect map-reduce explosions",
    )
    fan_out_threshold: int = Field(
        default=50,
        description="Threshold for fan-out detection",
    )
    max_batch_size: int = Field(
        default=1000,
        description="Maximum items in a single batch",
    )
    enforcement_level: EnforcementLevel = Field(
        default=EnforcementLevel.BLOCK,
        description="Enforcement level for violations",
    )


class ToolCallSpec(BaseModel):
    """Specification for a tool call (for plan checking)."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class PlanShapeGuard(BaseGuard):
    """Guard that detects pathological execution patterns.

    Features:
    - Cap tool-chain length
    - Cap unique tools per run
    - Detect fan-out explosions
    - Detect fan-out-then-fan-in patterns (map-reduce bombs)
    """

    def __init__(self, config: PlanShapeConfig | None = None) -> None:
        self.config = config or PlanShapeConfig()
        self._state = PlanShapeState()

    def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],  # noqa: ARG002
    ) -> GuardResult:
        """Check single tool call against plan shape constraints."""
        violations: list[PlanShapeViolation] = []

        # Check chain length (incremented after this call)
        if self._state.chain_depth >= self.config.max_chain_length:
            violations.append(
                PlanShapeViolation(
                    violation_type=PlanShapeViolationType.CHAIN_TOO_LONG,
                    limit=self.config.max_chain_length,
                    actual=self._state.chain_depth + 1,
                    detail=f"Chain depth would exceed {self.config.max_chain_length}",
                )
            )

        # Check unique tools (if new)
        if tool_name not in self._state.tools_seen:
            new_count = len(self._state.tools_seen) + 1
            if new_count > self.config.max_unique_tools:
                violations.append(
                    PlanShapeViolation(
                        violation_type=PlanShapeViolationType.TOO_MANY_UNIQUE_TOOLS,
                        limit=self.config.max_unique_tools,
                        actual=new_count,
                        detail=f"Would exceed {self.config.max_unique_tools} unique tools",
                    )
                )

        if violations:
            return self._create_violation_result(violations)

        return self.allow()

    def check_plan(
        self,
        plan: list[ToolCallSpec],
    ) -> GuardResult:
        """Check an entire plan before execution."""
        violations: list[PlanShapeViolation] = []

        # Check batch size
        if len(plan) > self.config.max_batch_size:
            violations.append(
                PlanShapeViolation(
                    violation_type=PlanShapeViolationType.BATCH_TOO_LARGE,
                    limit=self.config.max_batch_size,
                    actual=len(plan),
                    detail=f"Batch contains {len(plan)} items",
                )
            )

        # Check unique tools
        unique_tools = {call.tool_name for call in plan}
        if len(unique_tools) > self.config.max_unique_tools:
            violations.append(
                PlanShapeViolation(
                    violation_type=PlanShapeViolationType.TOO_MANY_UNIQUE_TOOLS,
                    limit=self.config.max_unique_tools,
                    actual=len(unique_tools),
                    detail=f"Plan uses {len(unique_tools)} unique tools",
                )
            )

        # Check fan-out
        fan_out_violation = self._check_fan_out(plan)
        if fan_out_violation:
            violations.append(fan_out_violation)

        # Check fan-out-fan-in pattern
        if self.config.detect_fan_out_fan_in:
            fofi_violation = self._check_fan_out_fan_in(plan)
            if fofi_violation:
                violations.append(fofi_violation)

        # Check chain length (by analyzing dependencies)
        chain_violation = self._check_chain_length(plan)
        if chain_violation:
            violations.append(chain_violation)

        if violations:
            return self._create_violation_result(violations)

        return self.allow()

    def check_batch(
        self,
        calls: list[tuple[str, dict[str, Any]]],
    ) -> GuardResult:
        """Check a batch of parallel calls."""
        violations: list[PlanShapeViolation] = []

        # Check batch size
        if len(calls) > self.config.max_batch_size:
            violations.append(
                PlanShapeViolation(
                    violation_type=PlanShapeViolationType.BATCH_TOO_LARGE,
                    limit=self.config.max_batch_size,
                    actual=len(calls),
                )
            )

        # Check fan-out
        if len(calls) > self.config.max_fan_out:
            violations.append(
                PlanShapeViolation(
                    violation_type=PlanShapeViolationType.FAN_OUT_TOO_LARGE,
                    limit=self.config.max_fan_out,
                    actual=len(calls),
                )
            )

        # Check unique tools
        unique_tools = {call[0] for call in calls}
        current_total = len(self._state.tools_seen | unique_tools)
        if current_total > self.config.max_unique_tools:
            violations.append(
                PlanShapeViolation(
                    violation_type=PlanShapeViolationType.TOO_MANY_UNIQUE_TOOLS,
                    limit=self.config.max_unique_tools,
                    actual=current_total,
                )
            )

        if violations:
            return self._create_violation_result(violations)

        return self.allow()

    def record_call(self, tool_name: str) -> None:
        """Record a tool call execution."""
        self._state.chain_depth += 1
        self._state.tools_seen.add(tool_name)
        self._state.total_calls += 1

    def record_fan_out(self, count: int) -> None:
        """Record a fan-out event."""
        self._state.current_fan_out = count
        self._state.max_fan_out_seen = max(self._state.max_fan_out_seen, count)

    def record_fan_in(self) -> None:
        """Record a fan-in event (parallel results merged)."""
        self._state.current_fan_out = 0

    def get_state(self) -> PlanShapeState:
        """Get current state."""
        return self._state.model_copy()

    def reset(self) -> None:
        """Reset state for new run."""
        self._state = PlanShapeState()

    def _check_fan_out(self, plan: list[ToolCallSpec]) -> PlanShapeViolation | None:
        """Check for excessive fan-out in plan."""
        # Count calls with same dependencies (parallel calls)
        dependency_groups: dict[tuple[str, ...], int] = {}

        for call in plan:
            dep_key = tuple(sorted(call.depends_on))
            dependency_groups[dep_key] = dependency_groups.get(dep_key, 0) + 1

        max_parallel = max(dependency_groups.values()) if dependency_groups else 0

        if max_parallel > self.config.max_fan_out:
            return PlanShapeViolation(
                violation_type=PlanShapeViolationType.FAN_OUT_TOO_LARGE,
                limit=self.config.max_fan_out,
                actual=max_parallel,
                detail=f"{max_parallel} parallel calls detected",
            )

        return None

    def _check_fan_out_fan_in(
        self,
        plan: list[ToolCallSpec],
    ) -> PlanShapeViolation | None:
        """Detect fan-out-then-fan-in patterns (map-reduce bombs)."""
        # Track dependent counts for fan-out detection

        # Find nodes with many dependents (fan-out sources)
        dependent_counts: dict[str, int] = {}
        for call in plan:
            for dep in call.depends_on:
                dependent_counts[dep] = dependent_counts.get(dep, 0) + 1

        # Check for large fan-out followed by fan-in
        for source_id, count in dependent_counts.items():
            if count >= self.config.fan_out_threshold:
                # Check if results are aggregated (fan-in)
                # This is a simplified heuristic
                return PlanShapeViolation(
                    violation_type=PlanShapeViolationType.FAN_OUT_FAN_IN_DETECTED,
                    limit=self.config.fan_out_threshold,
                    actual=count,
                    detail=f"Fan-out of {count} from '{source_id}' detected",
                )

        return None

    def _check_chain_length(
        self,
        plan: list[ToolCallSpec],
    ) -> PlanShapeViolation | None:
        """Check maximum chain length in plan."""
        # Build dependency graph and find longest path
        if not plan:
            return None

        # Simple topological analysis
        # This is a simplified check - just counts max sequential dependencies
        max_depth = 0

        for call in plan:
            depth = len(call.depends_on) + 1
            max_depth = max(max_depth, depth)

        if max_depth > self.config.max_chain_length:
            return PlanShapeViolation(
                violation_type=PlanShapeViolationType.CHAIN_TOO_LONG,
                limit=self.config.max_chain_length,
                actual=max_depth,
                detail=f"Chain depth of {max_depth} detected",
            )

        return None

    def _create_violation_result(
        self,
        violations: list[PlanShapeViolation],
    ) -> GuardResult:
        """Create result from violations."""
        messages = [f"{v.violation_type.value}: {v.actual} > {v.limit}" for v in violations]
        message = f"Plan shape violations: {'; '.join(messages)}"

        if self.config.enforcement_level == EnforcementLevel.WARN:
            return self.warn(
                reason=message,
                violations=[v.model_dump() for v in violations],
            )

        return self.block(
            reason=message,
            violations=[v.model_dump() for v in violations],
        )
