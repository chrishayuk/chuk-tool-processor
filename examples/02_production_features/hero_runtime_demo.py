#!/usr/bin/env python3
"""
Hero Runtime Demo: 8 Tools, 5 Seconds, 3 Pools

This demo showcases CHUK Tool Processor as a production tool execution runtime,
combining all major features:
- DAG scheduling with dependencies
- Bulkheads with per-pool concurrency limits
- ExecutionContext with deadline
- Parallel execution with streaming
- Return order control
- Scheduler explainability

Scenario: An e-commerce order processing pipeline that fetches data from multiple
sources, processes it, and stores the result - all within a 5-second deadline.

Usage:
    python examples/02_production_features/hero_runtime_demo.py
"""

import asyncio
import random
import time
from datetime import UTC, datetime

from chuk_tool_processor import (
    ExecutionContext,
    ToolProcessor,
    create_registry,
)
from chuk_tool_processor.execution.bulkhead import Bulkhead, BulkheadConfig
from chuk_tool_processor.scheduling import (
    GreedyDagScheduler,
    SchedulingConstraints,
    ToolCallSpec,
    ToolMetadata,
)

# ==============================================================================
# Mock Tools (simulating real operations with realistic latencies)
# ==============================================================================


class FetchUserTool:
    """Fetch user profile from user service."""

    async def execute(self, user_id: str) -> dict:
        await asyncio.sleep(random.uniform(0.1, 0.3))  # 100-300ms
        return {
            "user_id": user_id,
            "name": "Alice Smith",
            "tier": "premium",
            "fetched_at": datetime.now(UTC).isoformat(),
        }


class FetchOrdersTool:
    """Fetch recent orders from order service."""

    async def execute(self, user_id: str, limit: int = 10) -> dict:
        await asyncio.sleep(random.uniform(0.2, 0.4))  # 200-400ms
        return {
            "user_id": user_id,
            "orders": [{"order_id": f"ORD-{i}", "amount": 100 + i * 10} for i in range(limit)],
            "fetched_at": datetime.now(UTC).isoformat(),
        }


class FetchInventoryTool:
    """Fetch inventory status from warehouse service."""

    async def execute(self, product_ids: list[str]) -> dict:
        await asyncio.sleep(random.uniform(0.15, 0.35))  # 150-350ms
        return {
            "inventory": {pid: random.randint(0, 100) for pid in product_ids},
            "fetched_at": datetime.now(UTC).isoformat(),
        }


class AggregateTool:
    """Aggregate data from multiple sources."""

    async def execute(self, user_data: dict, order_data: dict) -> dict:
        await asyncio.sleep(random.uniform(0.1, 0.2))  # 100-200ms
        total_spend = sum(o["amount"] for o in order_data.get("orders", []))
        return {
            "user_id": user_data["user_id"],
            "user_tier": user_data["tier"],
            "total_orders": len(order_data.get("orders", [])),
            "total_spend": total_spend,
            "aggregated_at": datetime.now(UTC).isoformat(),
        }


class RecommendTool:
    """Generate recommendations based on aggregated data."""

    async def execute(self, aggregate: dict, inventory: dict) -> dict:
        await asyncio.sleep(random.uniform(0.15, 0.25))  # 150-250ms
        in_stock = [pid for pid, qty in inventory.get("inventory", {}).items() if qty > 10]
        return {
            "user_id": aggregate["user_id"],
            "recommendations": in_stock[:5],
            "personalized": aggregate["user_tier"] == "premium",
            "generated_at": datetime.now(UTC).isoformat(),
        }


class StoreResultTool:
    """Store processing result to database."""

    async def execute(self, result: dict, request_id: str) -> dict:
        await asyncio.sleep(random.uniform(0.05, 0.15))  # 50-150ms
        return {
            "stored": True,
            "request_id": request_id,
            "stored_at": datetime.now(UTC).isoformat(),
        }


class AnalyticsLogTool:
    """Log analytics event (optional, low priority)."""

    async def execute(self, event_type: str, data: dict) -> dict:
        await asyncio.sleep(random.uniform(0.1, 0.2))  # 100-200ms
        return {
            "logged": True,
            "event_type": event_type,
            "logged_at": datetime.now(UTC).isoformat(),
        }


# ==============================================================================
# Demo Implementation
# ==============================================================================


def print_timeline(events: list[tuple[float, str, str]]):
    """Print a visual timeline of events."""
    if not events:
        return

    start_time = events[0][0]
    print("\n" + "=" * 70)
    print("EXECUTION TIMELINE")
    print("=" * 70)

    for timestamp, event_type, description in sorted(events):
        elapsed = (timestamp - start_time) * 1000
        marker = ">>>" if event_type == "START" else "<<<" if event_type == "END" else "..."
        print(f"  {elapsed:7.1f}ms {marker} {description}")

    total_time = (events[-1][0] - start_time) * 1000
    print("-" * 70)
    print(f"  Total execution time: {total_time:.1f}ms")
    print("=" * 70)


async def demo_scheduler_planning():
    """Demonstrate DAG scheduling with explainability."""
    print("\n" + "=" * 70)
    print("PHASE 1: DAG SCHEDULING WITH EXPLAINABILITY")
    print("=" * 70)

    scheduler = GreedyDagScheduler(default_est_ms=200)

    # Define the 8-tool DAG
    calls = [
        # Stage 1: Parallel web fetches (no dependencies)
        ToolCallSpec(
            call_id="fetch-user",
            tool_name="web.fetch_user",
            args={"user_id": "user-123"},
            metadata=ToolMetadata(pool="web", est_ms=200, priority=10),
        ),
        ToolCallSpec(
            call_id="fetch-orders",
            tool_name="web.fetch_orders",
            args={"user_id": "user-123", "limit": 5},
            metadata=ToolMetadata(pool="web", est_ms=300, priority=10),
        ),
        ToolCallSpec(
            call_id="fetch-inventory",
            tool_name="web.fetch_inventory",
            args={"product_ids": ["PROD-1", "PROD-2", "PROD-3"]},
            metadata=ToolMetadata(pool="web", est_ms=250, priority=10),
        ),
        # Stage 2: Compute (depends on web fetches)
        ToolCallSpec(
            call_id="aggregate",
            tool_name="compute.aggregate",
            depends_on=("fetch-user", "fetch-orders"),
            metadata=ToolMetadata(pool="compute", est_ms=150, priority=10),
        ),
        ToolCallSpec(
            call_id="recommend",
            tool_name="compute.recommend",
            depends_on=("aggregate", "fetch-inventory"),
            metadata=ToolMetadata(pool="compute", est_ms=200, priority=10),
        ),
        # Stage 3: Database (depends on compute)
        ToolCallSpec(
            call_id="store",
            tool_name="db.store_result",
            depends_on=("recommend",),
            metadata=ToolMetadata(pool="db", est_ms=100, priority=10),
        ),
        # Stage 4: Analytics (optional, low priority)
        ToolCallSpec(
            call_id="analytics-1",
            tool_name="analytics.log",
            depends_on=("store",),
            metadata=ToolMetadata(pool="analytics", est_ms=150, priority=0),
        ),
        ToolCallSpec(
            call_id="analytics-2",
            tool_name="analytics.log",
            depends_on=("store",),
            metadata=ToolMetadata(pool="analytics", est_ms=150, priority=0),
        ),
    ]

    # Plan with constraints
    constraints = SchedulingConstraints(
        deadline_ms=5000,  # 5 second deadline
        pool_limits={"web": 3, "compute": 2, "db": 1, "analytics": 2},
    )

    plan = scheduler.plan(calls, constraints)

    # Display the plan
    print("\nDAG Structure:")
    print("  fetch-user ─────┐")
    print("                  ├─> aggregate ─┐")
    print("  fetch-orders ───┘              │")
    print("                                 ├─> recommend ─> store ─> analytics")
    print("  fetch-inventory ───────────────┘")

    print(f"\nExecution Plan ({len(plan.stages)} stages):")
    for i, stage in enumerate(plan.stages):
        print(f"  Stage {i + 1}: {', '.join(stage)}")

    if plan.skip:
        print(f"\nSkipped (deadline/priority): {', '.join(plan.skip)}")
        for reason in plan.skip_reasons:
            print(f"    - {reason.call_id}: {reason.reason}")
            if reason.detail:
                print(f"      {reason.detail}")

    print(f"\nExplainability Metrics:")
    print(f"  Critical path: {plan.critical_path_ms}ms")
    print(f"  Estimated total: {plan.estimated_total_ms}ms")
    print(f"  Pool utilization: {plan.pool_utilization}")

    return plan


async def demo_bulkhead_execution():
    """Demonstrate bulkhead-protected execution."""
    print("\n" + "=" * 70)
    print("PHASE 2: BULKHEAD-PROTECTED EXECUTION")
    print("=" * 70)

    # Configure bulkheads
    config = BulkheadConfig(
        default_limit=10,
        patterns={
            "web.*": 3,  # Max 3 concurrent web calls
            "compute.*": 2,  # Max 2 concurrent compute calls
            "db.*": 1,  # Max 1 concurrent db call
            "analytics.*": 2,  # Max 2 concurrent analytics calls
        },
        global_limit=10,
        acquisition_timeout=2.0,
    )

    bulkhead = Bulkhead(config)

    print("\nBulkhead Configuration:")
    print(f"  web.*: {config.patterns.get('web.*')} concurrent")
    print(f"  compute.*: {config.patterns.get('compute.*')} concurrent")
    print(f"  db.*: {config.patterns.get('db.*')} concurrent")
    print(f"  analytics.*: {config.patterns.get('analytics.*')} concurrent")
    print(f"  Global limit: {config.global_limit}")

    return bulkhead


async def demo_full_execution(plan, bulkhead):
    """Execute the full pipeline with all features."""
    print("\n" + "=" * 70)
    print("PHASE 3: FULL PIPELINE EXECUTION")
    print("=" * 70)

    # Create registry and register tools using dotted names
    # Dotted names are auto-parsed: "web.fetch_user" -> namespace="web", name="fetch_user"
    registry = create_registry()
    await registry.register_tool(FetchUserTool, name="web.fetch_user")
    await registry.register_tool(FetchOrdersTool, name="web.fetch_orders")
    await registry.register_tool(FetchInventoryTool, name="web.fetch_inventory")
    await registry.register_tool(AggregateTool, name="compute.aggregate")
    await registry.register_tool(RecommendTool, name="compute.recommend")
    await registry.register_tool(StoreResultTool, name="db.store_result")
    await registry.register_tool(AnalyticsLogTool, name="analytics.log")

    # Create execution context with deadline
    ctx = ExecutionContext.with_deadline(
        seconds=5,
        request_id="demo-request-001",
        user_id="user-123",
        tenant_id="acme-corp",
    )

    print(f"\nExecution Context:")
    print(f"  Request ID: {ctx.request_id}")
    print(f"  User ID: {ctx.user_id}")
    print(f"  Tenant ID: {ctx.tenant_id}")
    print(f"  Deadline: {ctx.deadline}")
    print(f"  Remaining: {ctx.remaining_time:.2f}s")

    # Create processor
    processor = ToolProcessor(
        registry=registry,
        enable_caching=True,
        enable_retries=True,
        max_retries=1,
    )

    # Track execution timeline
    events: list[tuple[float, str, str]] = []
    start_time = time.time()
    results = {}

    async def execute_with_tracking(call_id: str, tool_name: str, args: dict):
        """Execute a tool call with timeline tracking."""
        events.append((time.time(), "START", f"{call_id} ({tool_name})"))

        try:
            # Acquire bulkhead slot
            async with bulkhead.acquire(tool_name):
                # Execute through processor
                result = await processor.process(
                    [{"tool": tool_name, "arguments": args}],
                    context=ctx,
                )
                results[call_id] = result[0].result if result else None
                events.append((time.time(), "END", f"{call_id} -> OK"))
                return results[call_id]
        except Exception as e:
            events.append((time.time(), "ERROR", f"{call_id} -> {e}"))
            raise

    async with processor:
        print("\nExecuting stages...")

        # Execute each stage
        for stage_idx, stage in enumerate(plan.stages):
            print(f"\n  Stage {stage_idx + 1}: Starting {len(stage)} tools in parallel...")

            # Map call_id to (namespace.tool_name, args)
            # The tool name format is "namespace.tool" for proper resolution
            call_args = {
                "fetch-user": ("web.fetch_user", {"user_id": "user-123"}),
                "fetch-orders": ("web.fetch_orders", {"user_id": "user-123", "limit": 5}),
                "fetch-inventory": (
                    "web.fetch_inventory",
                    {"product_ids": ["PROD-1", "PROD-2", "PROD-3"]},
                ),
                "aggregate": (
                    "compute.aggregate",
                    {
                        "user_data": results.get("fetch-user", {}),
                        "order_data": results.get("fetch-orders", {}),
                    },
                ),
                "recommend": (
                    "compute.recommend",
                    {
                        "aggregate": results.get("aggregate", {}),
                        "inventory": results.get("fetch-inventory", {}),
                    },
                ),
                "store": (
                    "db.store_result",
                    {"result": results.get("recommend", {}), "request_id": ctx.request_id},
                ),
                "analytics-1": (
                    "analytics.log",
                    {"event_type": "order_processed", "data": {"user": "user-123"}},
                ),
                "analytics-2": (
                    "analytics.log",
                    {"event_type": "recommendations_generated", "data": {"count": 5}},
                ),
            }

            # Execute stage in parallel
            tasks = []
            for call_id in stage:
                if call_id in call_args:
                    tool_name, args = call_args[call_id]
                    tasks.append(execute_with_tracking(call_id, tool_name, args))

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    # Print timeline
    print_timeline(events)

    # Summary
    total_time = (time.time() - start_time) * 1000
    print(f"\nExecution Summary:")
    print(f"  Total tools executed: {len(results)}")
    print(f"  Total time: {total_time:.1f}ms")
    print(f"  Under deadline: {'Yes' if total_time < 5000 else 'No'}")
    print(f"  Context remaining: {ctx.remaining_time:.2f}s")

    return results


async def main():
    """Run the complete hero demo."""
    print("""
    ╔══════════════════════════════════════════════════════════════════════╗
    ║                                                                      ║
    ║         CHUK TOOL PROCESSOR - HERO RUNTIME DEMO                     ║
    ║                                                                      ║
    ║         8 Tools | 5 Second Deadline | 3 Pools                       ║
    ║                                                                      ║
    ╚══════════════════════════════════════════════════════════════════════╝

    This demo showcases the full production runtime capabilities:
    - DAG scheduling with topological ordering
    - Bulkheads with per-pool concurrency limits
    - ExecutionContext with deadline propagation
    - Parallel execution with completion-order streaming
    - Scheduler explainability (critical path, skip reasons)
    """)

    # Phase 1: Plan the DAG
    plan = await demo_scheduler_planning()

    # Phase 2: Configure bulkheads
    bulkhead = await demo_bulkhead_execution()

    # Phase 3: Execute with all features
    results = await demo_full_execution(plan, bulkhead)

    print("\n" + "=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
    print("""
    Key Takeaways:
    1. DAG scheduler respects dependencies and pool limits
    2. Bulkheads prevent any single pool from being overwhelmed
    3. ExecutionContext propagates deadline/tracing through pipeline
    4. Parallel execution + completion order minimizes total latency
    5. Skip reasons provide debugging visibility

    This is what "production-grade tool execution" looks like.
    """)


if __name__ == "__main__":
    asyncio.run(main())
