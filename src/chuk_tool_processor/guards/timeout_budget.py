# chuk_tool_processor/guards/timeout_budget.py
"""Timeout budget guard for enforcing wall-clock execution limits.

Enforces per-turn and per-plan time budgets with soft/hard limits.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from chuk_tool_processor.guards.base import BaseGuard, GuardResult
from chuk_tool_processor.guards.models import EnforcementLevel


class DegradeAction(str, Enum):
    """Actions to take when soft budget is exceeded."""

    DISABLE_RETRIES = "disable_retries"
    REDUCE_PARALLELISM = "reduce_parallelism"
    SKIP_OPTIONAL = "skip_optional"
    REDUCE_TIMEOUT = "reduce_timeout"


class BudgetStatus(str, Enum):
    """Current budget status."""

    OK = "ok"
    SOFT_LIMIT = "soft_limit"  # Degraded mode
    HARD_LIMIT = "hard_limit"  # Blocked


class TimeoutBudgetState(BaseModel):
    """Current timeout budget state."""

    turn_start_ms: int | None = None
    plan_start_ms: int | None = None
    turn_elapsed_ms: int = 0
    plan_elapsed_ms: int = 0
    executions: int = 0
    total_execution_ms: int = 0
    status: BudgetStatus = BudgetStatus.OK
    active_degrade_actions: list[DegradeAction] = Field(default_factory=list)


class TimeoutBudgetConfig(BaseModel):
    """Configuration for TimeoutBudgetGuard."""

    per_turn_budget_ms: int = Field(
        default=30_000,
        description="Maximum wall-clock time per turn (30s default)",
    )
    per_plan_budget_ms: int | None = Field(
        default=None,
        description="Maximum wall-clock time per plan (None = unlimited)",
    )
    soft_budget_ratio: float = Field(
        default=0.8,
        description="Ratio at which soft limit triggers (0.8 = 80%)",
    )
    degrade_actions: list[DegradeAction] = Field(
        default_factory=lambda: [
            DegradeAction.DISABLE_RETRIES,
            DegradeAction.REDUCE_PARALLELISM,
        ],
        description="Actions to take when soft budget exceeded",
    )
    enforcement_level: EnforcementLevel = Field(
        default=EnforcementLevel.BLOCK,
        description="Enforcement level for hard limit",
    )


class TimeoutBudgetGuard(BaseGuard):
    """Guard that enforces overall wall-clock budget.

    Features:
    - Per-turn time limits
    - Per-plan time limits
    - Soft budget triggers degrade mode
    - Hard budget blocks execution
    - Tracks execution statistics
    """

    def __init__(self, config: TimeoutBudgetConfig | None = None) -> None:
        self.config = config or TimeoutBudgetConfig()
        self._state = TimeoutBudgetState()

    def check(
        self,
        tool_name: str,  # noqa: ARG002
        arguments: dict[str, Any],  # noqa: ARG002
    ) -> GuardResult:
        """Check if execution is allowed based on time budget."""
        self._update_elapsed()

        # Check hard limits
        hard_violation = self._check_hard_limit()
        if hard_violation:
            return hard_violation

        # Check soft limits
        soft_violation = self._check_soft_limit()
        if soft_violation:
            return soft_violation

        return self.allow()

    def start_turn(self) -> None:
        """Start timing a new turn."""
        now_ms = self._now_ms()
        self._state.turn_start_ms = now_ms
        self._state.turn_elapsed_ms = 0
        self._state.executions = 0
        self._state.total_execution_ms = 0
        self._state.status = BudgetStatus.OK
        self._state.active_degrade_actions = []

    def start_plan(self) -> None:
        """Start timing a new plan."""
        now_ms = self._now_ms()
        self._state.plan_start_ms = now_ms
        self._state.plan_elapsed_ms = 0

    def end_turn(self) -> TimeoutBudgetState:
        """End timing for current turn. Returns final state."""
        self._update_elapsed()
        state = self._state.model_copy()
        self._state.turn_start_ms = None
        return state

    def end_plan(self) -> TimeoutBudgetState:
        """End timing for current plan. Returns final state."""
        self._update_elapsed()
        state = self._state.model_copy()
        self._state.plan_start_ms = None
        return state

    def record_execution(self, duration_ms: int) -> None:
        """Record a tool execution duration."""
        self._state.executions += 1
        self._state.total_execution_ms += duration_ms
        self._update_elapsed()

    def get_remaining_budget_ms(self) -> int:
        """Get remaining time budget in milliseconds."""
        self._update_elapsed()

        if self._state.turn_start_ms is None:
            return self.config.per_turn_budget_ms

        return max(0, self.config.per_turn_budget_ms - self._state.turn_elapsed_ms)

    def get_state(self) -> TimeoutBudgetState:
        """Get current state."""
        self._update_elapsed()
        return self._state.model_copy()

    def is_degraded(self) -> bool:
        """Check if currently in degraded mode."""
        self._update_elapsed()
        return self._state.status == BudgetStatus.SOFT_LIMIT

    def should_disable_retries(self) -> bool:
        """Check if retries should be disabled."""
        return DegradeAction.DISABLE_RETRIES in self._state.active_degrade_actions

    def should_reduce_parallelism(self) -> bool:
        """Check if parallelism should be reduced."""
        return DegradeAction.REDUCE_PARALLELISM in self._state.active_degrade_actions

    def reset(self) -> None:
        """Reset all state."""
        self._state = TimeoutBudgetState()

    def _update_elapsed(self) -> None:
        """Update elapsed time calculations."""
        now_ms = self._now_ms()

        if self._state.turn_start_ms is not None:
            self._state.turn_elapsed_ms = now_ms - self._state.turn_start_ms

        if self._state.plan_start_ms is not None:
            self._state.plan_elapsed_ms = now_ms - self._state.plan_start_ms

    def _check_hard_limit(self) -> GuardResult | None:
        """Check if hard time limit is exceeded."""
        # Turn budget
        if self._state.turn_elapsed_ms >= self.config.per_turn_budget_ms:
            self._state.status = BudgetStatus.HARD_LIMIT
            message = (
                f"Turn time budget exceeded: {self._state.turn_elapsed_ms}ms >= {self.config.per_turn_budget_ms}ms"
            )
            return self._enforcement_result(message)

        # Plan budget
        if self.config.per_plan_budget_ms is not None and self._state.plan_elapsed_ms >= self.config.per_plan_budget_ms:
            self._state.status = BudgetStatus.HARD_LIMIT
            message = (
                f"Plan time budget exceeded: {self._state.plan_elapsed_ms}ms >= {self.config.per_plan_budget_ms}ms"
            )
            return self._enforcement_result(message)

        return None

    def _check_soft_limit(self) -> GuardResult | None:
        """Check if soft time limit is exceeded (triggers degrade mode)."""
        soft_turn_limit = int(self.config.per_turn_budget_ms * self.config.soft_budget_ratio)

        if self._state.turn_elapsed_ms >= soft_turn_limit:
            self._state.status = BudgetStatus.SOFT_LIMIT
            self._state.active_degrade_actions = list(self.config.degrade_actions)

            return self.warn(
                reason=(
                    f"Soft time budget exceeded ({self._state.turn_elapsed_ms}ms "
                    f">= {soft_turn_limit}ms), entering degraded mode"
                ),
                elapsed_ms=self._state.turn_elapsed_ms,
                soft_limit_ms=soft_turn_limit,
                degrade_actions=[a.value for a in self._state.active_degrade_actions],
            )

        # Plan soft limit
        if self.config.per_plan_budget_ms is not None:
            soft_plan_limit = int(self.config.per_plan_budget_ms * self.config.soft_budget_ratio)
            if self._state.plan_elapsed_ms >= soft_plan_limit:
                self._state.status = BudgetStatus.SOFT_LIMIT
                self._state.active_degrade_actions = list(self.config.degrade_actions)

                return self.warn(
                    reason=(
                        f"Soft plan budget exceeded ({self._state.plan_elapsed_ms}ms "
                        f">= {soft_plan_limit}ms), entering degraded mode"
                    ),
                    elapsed_ms=self._state.plan_elapsed_ms,
                    soft_limit_ms=soft_plan_limit,
                    degrade_actions=[a.value for a in self._state.active_degrade_actions],
                )

        return None

    def _enforcement_result(self, message: str) -> GuardResult:
        """Create enforcement result based on config."""
        if self.config.enforcement_level == EnforcementLevel.WARN:
            return self.warn(
                reason=message,
                state=self._state.model_dump(),
            )

        return self.block(
            reason=message,
            state=self._state.model_dump(),
        )

    def _now_ms(self) -> int:
        """Get current time in milliseconds."""
        return int(time.time() * 1000)
