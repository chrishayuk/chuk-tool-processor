# chuk_tool_processor/scheduling/greedy_dag.py
"""
Greedy DAG scheduler implementation.

This scheduler provides deadline-aware scheduling with:
- Topological ordering for dependencies
- Priority-based ordering within ready sets
- Pool-based stage splitting
- Deadline-aware skipping of low-priority calls

It's a practical MVP scheduler that works well for most use cases
without requiring a constraint solver.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.scheduling.types import (
    ExecutionPlan,
    SchedulingConstraints,
    SkipReason,
    ToolCallSpec,
)

logger = get_logger("chuk_tool_processor.scheduling.greedy_dag")


class GreedyDagScheduler:
    """
    Greedy DAG scheduler with deadline awareness.

    This scheduler:
    1. Builds a dependency graph from call dependencies
    2. Performs topological sort to determine execution order
    3. Splits calls into stages based on pool limits
    4. Skips low-priority calls if deadline would be exceeded

    Example:
        >>> scheduler = GreedyDagScheduler()
        >>> calls = [
        ...     ToolCallSpec(call_id="1", tool_name="fetch"),
        ...     ToolCallSpec(call_id="2", tool_name="transform", depends_on=["1"]),
        ...     ToolCallSpec(call_id="3", tool_name="store", depends_on=["2"]),
        ... ]
        >>> plan = scheduler.plan(calls, SchedulingConstraints())
        >>> print(plan.stages)
        (('1',), ('2',), ('3',))
    """

    def __init__(
        self,
        default_est_ms: int = 1000,
        skip_threshold_ratio: float = 0.8,
    ) -> None:
        """
        Initialize the greedy DAG scheduler.

        Args:
            default_est_ms: Default estimated execution time for calls without est_ms
            skip_threshold_ratio: Skip calls if their completion would exceed
                                  this ratio of the deadline (0.8 = 80%)
        """
        self.default_est_ms = default_est_ms
        self.skip_threshold_ratio = skip_threshold_ratio

    def plan(
        self,
        calls: Sequence[ToolCallSpec],
        constraints: SchedulingConstraints,
        context: Mapping[str, object] | None = None,  # noqa: ARG002
    ) -> ExecutionPlan:
        """
        Create an execution plan for the given calls.

        Args:
            calls: Tool calls to schedule
            constraints: Global constraints (deadline, cost, pool limits)
            context: Optional request-scoped context (unused in greedy scheduler)

        Returns:
            An ExecutionPlan with stages, skips, and optional overrides
        """
        if not calls:
            return ExecutionPlan()

        # Build lookup maps
        call_map = {c.call_id: c for c in calls}
        call_ids = set(call_map.keys())

        logger.debug(
            "Planning %d calls with deadline=%s, pool_limits=%s",
            len(calls),
            constraints.deadline_ms,
            constraints.pool_limits,
        )

        # Step 1: Topological sort
        sorted_ids = self._topological_sort(calls, call_map)
        if sorted_ids is None:
            # Cycle detected - return empty plan with all calls skipped
            logger.warning("Dependency cycle detected, skipping all calls")
            return ExecutionPlan(skip=tuple(call_ids))

        # Step 2: Determine which calls to skip (deadline/cost constraints)
        skip_ids, skip_reasons = self._determine_skips(sorted_ids, call_map, constraints)
        scheduled_ids = [cid for cid in sorted_ids if cid not in skip_ids]

        # Step 3: Build stages respecting pool limits
        stages = self._build_stages(scheduled_ids, call_map, constraints)

        # Step 4: Calculate per-call timeout adjustments if deadline is set
        per_call_timeout_ms = {}
        if constraints.deadline_ms is not None:
            per_call_timeout_ms = self._calculate_timeouts(stages, call_map, constraints)

        # Step 5: Calculate explainability metrics
        critical_path_ms, estimated_total_ms = self._calculate_critical_path(stages, call_map)
        pool_utilization = self._calculate_pool_utilization(stages, call_map)

        logger.debug(
            "Plan created: %d stages, %d scheduled, %d skipped, critical_path=%dms",
            len(stages),
            len(scheduled_ids),
            len(skip_ids),
            critical_path_ms or 0,
        )

        return ExecutionPlan(
            stages=tuple(tuple(stage) for stage in stages),
            per_call_timeout_ms=per_call_timeout_ms,
            skip=tuple(skip_ids),
            skip_reasons=tuple(skip_reasons),
            critical_path_ms=critical_path_ms,
            estimated_total_ms=estimated_total_ms,
            pool_utilization=pool_utilization,
        )

    def _topological_sort(
        self,
        calls: Sequence[ToolCallSpec],
        call_map: dict[str, ToolCallSpec],
    ) -> list[str] | None:
        """
        Perform topological sort on calls based on dependencies.

        Uses Kahn's algorithm for simplicity and cycle detection.

        Args:
            calls: All tool calls
            call_map: Map of call_id -> ToolCallSpec

        Returns:
            List of call_ids in topological order, or None if cycle detected
        """
        # Build adjacency list and in-degree counts
        in_degree: dict[str, int] = defaultdict(int)
        dependents: dict[str, list[str]] = defaultdict(list)

        for call in calls:
            in_degree[call.call_id]  # Ensure all calls have an entry
            for dep in call.depends_on:
                if dep in call_map:  # Only count valid dependencies
                    dependents[dep].append(call.call_id)
                    in_degree[call.call_id] += 1

        # Find all calls with no dependencies (in_degree == 0)
        ready = [cid for cid, deg in in_degree.items() if deg == 0]

        # Sort by (priority desc, est_ms asc) for deterministic ordering
        def sort_key(cid: str) -> tuple[int, int]:
            call = call_map[cid]
            priority = -call.metadata.priority  # Negative for descending
            est = call.metadata.est_ms or self.default_est_ms
            return (priority, est)

        ready.sort(key=sort_key)

        result = []
        while ready:
            # Pop highest priority ready call
            current = ready.pop(0)
            result.append(current)

            # Update dependents
            for dep in dependents[current]:
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    ready.append(dep)
                    ready.sort(key=sort_key)

        # Check for cycles
        if len(result) != len(call_map):
            return None

        return result

    def _determine_skips(
        self,
        sorted_ids: list[str],
        call_map: dict[str, ToolCallSpec],
        constraints: SchedulingConstraints,
    ) -> tuple[set[str], list[SkipReason]]:
        """
        Determine which calls to skip based on deadline and cost constraints.

        Uses a greedy approach: process calls in priority order, skip if
        estimated completion would exceed deadline threshold.

        Args:
            sorted_ids: Topologically sorted call IDs
            call_map: Map of call_id -> ToolCallSpec
            constraints: Scheduling constraints

        Returns:
            Tuple of (set of call_ids to skip, list of skip reasons)
        """
        skip_ids: set[str] = set()
        skip_reasons: list[SkipReason] = []

        if constraints.deadline_ms is None and constraints.max_cost is None:
            return skip_ids, skip_reasons

        # Track cumulative time and cost
        cumulative_time_ms = constraints.now_ms
        cumulative_cost = 0.0

        # Calculate deadline threshold
        deadline_threshold = None
        if constraints.deadline_ms is not None:
            deadline_threshold = int(constraints.deadline_ms * self.skip_threshold_ratio)

        for call_id in sorted_ids:
            call = call_map[call_id]
            est_ms = call.metadata.est_ms or self.default_est_ms
            cost = call.metadata.cost or 0.0

            # Check if dependencies are skipped
            skipped_deps = [dep for dep in call.depends_on if dep in skip_ids]
            if skipped_deps:
                logger.debug("Skipping %s because dependency is skipped", call_id)
                skip_ids.add(call_id)
                skip_reasons.append(
                    SkipReason(
                        call_id=call_id,
                        reason="dependency_skipped",
                        detail=f"Depends on skipped call(s): {', '.join(skipped_deps)}",
                    )
                )
                continue

            # Check deadline constraint - skip low-priority calls that would exceed threshold
            if (
                deadline_threshold is not None
                and cumulative_time_ms + est_ms > deadline_threshold
                and call.metadata.priority <= 0
            ):
                logger.debug(
                    "Skipping %s: would exceed deadline threshold (%d + %d > %d)",
                    call_id,
                    cumulative_time_ms,
                    est_ms,
                    deadline_threshold,
                )
                skip_ids.add(call_id)
                skip_reasons.append(
                    SkipReason(
                        call_id=call_id,
                        reason="deadline_exceeded",
                        detail=f"Estimated completion {cumulative_time_ms + est_ms}ms > threshold {deadline_threshold}ms",
                    )
                )
                continue

            # Check cost constraint - skip low-priority calls that would exceed cost limit
            if (
                constraints.max_cost is not None
                and cumulative_cost + cost > constraints.max_cost
                and call.metadata.priority <= 0
            ):
                logger.debug(
                    "Skipping %s: would exceed cost limit (%.2f + %.2f > %.2f)",
                    call_id,
                    cumulative_cost,
                    cost,
                    constraints.max_cost,
                )
                skip_ids.add(call_id)
                skip_reasons.append(
                    SkipReason(
                        call_id=call_id,
                        reason="cost_exceeded",
                        detail=f"Cumulative cost {cumulative_cost + cost:.2f} > limit {constraints.max_cost:.2f}",
                    )
                )
                continue

            # Call is scheduled
            cumulative_time_ms += est_ms
            cumulative_cost += cost

        return skip_ids, skip_reasons

    def _build_stages(
        self,
        scheduled_ids: list[str],
        call_map: dict[str, ToolCallSpec],
        constraints: SchedulingConstraints,
    ) -> list[list[str]]:
        """
        Build execution stages respecting pool limits and dependencies.

        Calls are grouped into stages where:
        - All dependencies are in earlier stages
        - Pool limits are not exceeded within a stage

        Args:
            scheduled_ids: Topologically sorted call IDs (not skipped)
            call_map: Map of call_id -> ToolCallSpec
            constraints: Scheduling constraints with pool limits

        Returns:
            List of stages, each containing call_ids
        """
        if not scheduled_ids:
            return []

        # Track which calls have completed (in earlier stages)
        completed: set[str] = set()
        stages: list[list[str]] = []

        remaining = list(scheduled_ids)

        while remaining:
            # Find calls that are ready (all deps completed)
            ready = [cid for cid in remaining if all(dep in completed for dep in call_map[cid].depends_on)]

            if not ready:
                # Should not happen if topological sort is correct
                logger.error("No ready calls but remaining: %s", remaining)
                break

            # Build stage respecting pool limits
            stage: list[str] = []
            pool_counts: dict[str, int] = defaultdict(int)

            for call_id in ready:
                call = call_map[call_id]
                pool = call.metadata.pool
                limit = constraints.pool_limits.get(pool, float("inf"))

                if pool_counts[pool] < limit:
                    stage.append(call_id)
                    pool_counts[pool] += 1

            if not stage:
                # Pool limits prevent any progress - add first ready call anyway
                # to avoid infinite loop
                stage.append(ready[0])

            stages.append(stage)
            completed.update(stage)
            remaining = [cid for cid in remaining if cid not in completed]

        return stages

    def _calculate_timeouts(
        self,
        stages: list[list[str]],
        call_map: dict[str, ToolCallSpec],
        constraints: SchedulingConstraints,
    ) -> dict[str, int]:
        """
        Calculate per-call timeout adjustments to meet deadline.

        Distributes remaining time budget across stages, giving more time
        to earlier stages and critical path calls.

        Args:
            stages: Execution stages
            call_map: Map of call_id -> ToolCallSpec
            constraints: Scheduling constraints

        Returns:
            Map of call_id -> timeout_ms
        """
        if constraints.deadline_ms is None:
            return {}

        per_call_timeout_ms: dict[str, int] = {}
        remaining_budget = constraints.deadline_ms - constraints.now_ms

        for stage_idx, stage in enumerate(stages):
            # Calculate stage budget (proportional to remaining stages)
            remaining_stages = len(stages) - stage_idx
            stage_budget = remaining_budget // remaining_stages

            # Find max estimated time in this stage
            max_est = max(call_map[cid].metadata.est_ms or self.default_est_ms for cid in stage)

            # Stage timeout is max of estimated time and proportional budget
            stage_timeout = max(max_est, stage_budget)

            for call_id in stage:
                call = call_map[call_id]
                # Use call-specific timeout if set, otherwise stage timeout
                if call.timeout_ms is not None:
                    per_call_timeout_ms[call_id] = call.timeout_ms
                else:
                    per_call_timeout_ms[call_id] = stage_timeout

            remaining_budget -= stage_timeout

        return per_call_timeout_ms

    def _calculate_critical_path(
        self,
        stages: list[list[str]],
        call_map: dict[str, ToolCallSpec],
    ) -> tuple[int | None, int | None]:
        """
        Calculate critical path and estimated total execution time.

        Critical path = sum of max est_ms per stage (worst-case serial path).
        Estimated total = same as critical path when executing stages sequentially.

        Args:
            stages: Execution stages
            call_map: Map of call_id -> ToolCallSpec

        Returns:
            Tuple of (critical_path_ms, estimated_total_ms)
        """
        if not stages:
            return None, None

        critical_path_ms = 0
        for stage in stages:
            if stage:
                max_stage_ms = max(call_map[cid].metadata.est_ms or self.default_est_ms for cid in stage)
                critical_path_ms += max_stage_ms

        return critical_path_ms, critical_path_ms

    def _calculate_pool_utilization(
        self,
        stages: list[list[str]],
        call_map: dict[str, ToolCallSpec],
    ) -> dict[str, int]:
        """
        Calculate per-pool max concurrent calls across all stages.

        Args:
            stages: Execution stages
            call_map: Map of call_id -> ToolCallSpec

        Returns:
            Map of pool -> max concurrent calls in any stage
        """
        pool_max: dict[str, int] = defaultdict(int)

        for stage in stages:
            pool_counts: dict[str, int] = defaultdict(int)
            for call_id in stage:
                pool = call_map[call_id].metadata.pool
                pool_counts[pool] += 1

            for pool, count in pool_counts.items():
                pool_max[pool] = max(pool_max[pool], count)

        return dict(pool_max)
