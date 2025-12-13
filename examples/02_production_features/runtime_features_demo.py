#!/usr/bin/env python
"""
Runtime Features Demo - Advanced Scheduling, Return Order, and Pattern Bulkheads

This example demonstrates the new runtime features:

1. **Return Order** - Control whether results stream back in completion or submission order
2. **Pattern-Based Bulkheads** - Use glob patterns like "db.*" or "mcp.notion.*" for concurrency
3. **SchedulerPolicy** - DAG-based scheduling with dependencies, deadlines, and pool limits

These features transform chuk-tool-processor from a "tool executor" into a proper
tool execution runtime.

Running the demo:
    python examples/02_production_features/runtime_features_demo.py
"""

import asyncio
import random

from chuk_tool_processor import (
    BulkheadConfig,
    ExecutionPlan,
    GreedyDagScheduler,
    ReturnOrder,
    SchedulingConstraints,
    ToolCallSpec,
    ToolMetadata,
    ToolProcessor,
    create_registry,
)


# ------------------------------------------------------------------
# Example tools with varying execution times
# ------------------------------------------------------------------
class FastTool:
    """A fast tool that completes in ~50ms."""

    async def execute(self, message: str = "fast") -> dict:
        delay = 0.05 + random.uniform(0, 0.02)
        await asyncio.sleep(delay)
        return {"response": f"Fast: {message}", "delay_ms": int(delay * 1000)}


class MediumTool:
    """A medium-speed tool that completes in ~200ms."""

    async def execute(self, data: str = "medium") -> dict:
        delay = 0.2 + random.uniform(0, 0.05)
        await asyncio.sleep(delay)
        return {"response": f"Medium: {data}", "delay_ms": int(delay * 1000)}


class SlowTool:
    """A slow tool that completes in ~500ms."""

    async def execute(self, query: str = "slow") -> dict:
        delay = 0.5 + random.uniform(0, 0.1)
        await asyncio.sleep(delay)
        return {"response": f"Slow: {query}", "delay_ms": int(delay * 1000)}


class DatabaseReadTool:
    """Simulates a database read operation."""

    async def execute(self, table: str = "users") -> dict:
        await asyncio.sleep(0.1)
        return {"table": table, "rows": 42}


class DatabaseWriteTool:
    """Simulates a database write operation."""

    async def execute(self, table: str = "users", data: str = "{}") -> dict:
        await asyncio.sleep(0.15)
        return {"table": table, "written": True}


class WebFetchTool:
    """Simulates fetching from an external web API."""

    async def execute(self, url: str = "https://api.example.com") -> dict:
        await asyncio.sleep(0.3)
        return {"url": url, "status": 200}


class MCPNotionTool:
    """Simulates an MCP Notion integration tool."""

    async def execute(self, page_id: str = "abc123") -> dict:
        await asyncio.sleep(0.25)
        return {"page_id": page_id, "synced": True}


class MCPGitHubTool:
    """Simulates an MCP GitHub integration tool."""

    async def execute(self, repo: str = "owner/repo") -> dict:
        await asyncio.sleep(0.2)
        return {"repo": repo, "stars": 100}


# ------------------------------------------------------------------
# Demo 1: Return Order - Completion vs Submission
# ------------------------------------------------------------------
async def demo_return_order():
    print("=" * 70)
    print("Demo 1: Return Order - Completion vs Submission")
    print("=" * 70)
    print()
    print("Results can be returned in two orders:")
    print("  - COMPLETION: Results stream back as tools finish (faster tools first)")
    print("  - SUBMISSION: Results return in the same order as submitted")
    print()

    registry = create_registry()
    await registry.register_tool(FastTool, name="fast_tool")
    await registry.register_tool(MediumTool, name="medium_tool")
    await registry.register_tool(SlowTool, name="slow_tool")

    processor = ToolProcessor(registry=registry)
    await processor.initialize()

    # Three calls with different execution times
    calls = [
        {"tool": "slow_tool", "arguments": {"query": "call-1-slow"}},     # ~500ms
        {"tool": "medium_tool", "arguments": {"data": "call-2-medium"}}, # ~200ms
        {"tool": "fast_tool", "arguments": {"message": "call-3-fast"}},  # ~50ms
    ]

    # Demo completion order
    print("  COMPLETION order (default):")
    print("  Tools: slow(~500ms), medium(~200ms), fast(~50ms)")
    results = await processor.process(calls, return_order=ReturnOrder.COMPLETION)
    print("  Received order:", [r.result.get("response", "?").split(":")[0] for r in results])
    print("  -> Fast tools return first without waiting for slow ones!")
    print()

    # Demo submission order
    print("  SUBMISSION order:")
    results = await processor.process(calls, return_order=ReturnOrder.SUBMISSION)
    print("  Received order:", [r.result.get("response", "?").split(":")[0] for r in results])
    print("  -> Results return in exact submission order (slow, medium, fast)")
    print()

    # Show call_id tracking
    print("  Each result tracks its original call_id for correlation:")
    for r in results:
        print(f"    - call_id: {r.call_id}, tool: {r.tool}")
    print()


# ------------------------------------------------------------------
# Demo 2: Pattern-Based Bulkheads
# ------------------------------------------------------------------
async def demo_pattern_bulkheads():
    print("=" * 70)
    print("Demo 2: Pattern-Based Bulkheads")
    print("=" * 70)
    print()
    print("Group tools by pattern for shared concurrency limits:")
    print("  - 'db.*' matches db.read, db.write, db.backup, etc.")
    print("  - 'mcp.notion.*' matches all Notion MCP tools")
    print()

    from chuk_tool_processor import Bulkhead

    # Configure bulkhead with patterns
    config = BulkheadConfig(
        default_limit=10,
        patterns={
            "db.*": 3,           # All database tools share 3 slots
            "mcp.notion.*": 2,   # All Notion tools share 2 slots
            "mcp.*": 5,          # Other MCP tools share 5 slots
            "web.*": 4,          # Web tools share 4 slots
        },
        global_limit=20,
    )

    bulkhead = Bulkhead(config)

    print("  Pattern Configuration:")
    for pattern, limit in config.patterns.items():
        print(f"    • '{pattern}': {limit} concurrent")
    print()

    # Show which limits apply to which tools
    test_tools = [
        "db.read", "db.write", "db.backup",
        "mcp.notion.search", "mcp.notion.create",
        "mcp.github.issues", "mcp.slack.send",
        "web.fetch", "web.scrape",
        "other_tool",
    ]

    print("  Tool -> Effective Limit:")
    for tool in test_tools:
        limit = bulkhead._get_limit_for_tool(tool)
        print(f"    • {tool:20} -> limit={limit}")
    print()

    # Demonstrate pattern-based concurrency
    print("  Running 5 concurrent 'db.*' calls with limit=3...")

    async def db_operation(name: str):
        async with bulkhead.acquire(name):
            await asyncio.sleep(0.2)
            return f"{name} done"

    start = asyncio.get_event_loop().time()
    db_tasks = [
        db_operation(f"db.op{i}")
        for i in range(5)
    ]
    await asyncio.gather(*db_tasks)
    elapsed = asyncio.get_event_loop().time() - start

    print(f"    ✓ 5 calls completed in {elapsed:.2f}s")
    print("    (With limit=3 and 0.2s/call: 3 parallel + 2 parallel = ~0.4s expected)")
    print()


# ------------------------------------------------------------------
# Demo 3: SchedulerPolicy and DAG Scheduling
# ------------------------------------------------------------------
async def demo_scheduler_policy():
    print("=" * 70)
    print("Demo 3: SchedulerPolicy and DAG Scheduling")
    print("=" * 70)
    print()
    print("Create execution plans with:")
    print("  - Dependencies between tool calls")
    print("  - Pool-based concurrency limits")
    print("  - Deadline-aware scheduling")
    print("  - Priority-based ordering")
    print()

    scheduler = GreedyDagScheduler(
        default_est_ms=1000,     # Default estimated time
        skip_threshold_ratio=0.8,  # Skip low-priority calls if near deadline
    )

    # Create a DAG of tool calls
    # Scenario: ETL pipeline with fetch -> transform -> store
    calls = [
        # Stage 1: Parallel fetches
        ToolCallSpec(
            call_id="fetch-users",
            tool_name="web.fetch",
            args={"url": "/api/users"},
            metadata=ToolMetadata(pool="web", est_ms=300, priority=10),
        ),
        ToolCallSpec(
            call_id="fetch-orders",
            tool_name="web.fetch",
            args={"url": "/api/orders"},
            metadata=ToolMetadata(pool="web", est_ms=300, priority=10),
        ),
        # Stage 2: Transform (depends on fetches)
        ToolCallSpec(
            call_id="transform",
            tool_name="compute.transform",
            args={"mode": "join"},
            depends_on=("fetch-users", "fetch-orders"),
            metadata=ToolMetadata(pool="compute", est_ms=500, priority=10),
        ),
        # Stage 3: Store (depends on transform)
        ToolCallSpec(
            call_id="store-db",
            tool_name="db.write",
            args={"table": "combined"},
            depends_on=("transform",),
            metadata=ToolMetadata(pool="db", est_ms=200, priority=10),
        ),
        # Optional: Low-priority analytics (may be skipped under deadline)
        ToolCallSpec(
            call_id="analytics",
            tool_name="analytics.log",
            args={"event": "etl-complete"},
            depends_on=("store-db",),
            metadata=ToolMetadata(pool="analytics", est_ms=100, priority=0),
        ),
    ]

    print("  DAG Structure:")
    print("    fetch-users ──┐")
    print("                  ├─> transform ──> store-db ──> analytics")
    print("    fetch-orders ─┘")
    print()

    # Create plan without constraints
    print("  Plan without deadline:")
    constraints = SchedulingConstraints(
        pool_limits={"web": 2, "db": 1, "compute": 1},
    )
    plan = scheduler.plan(calls, constraints)

    print(f"    Stages: {len(plan.stages)}")
    for i, stage in enumerate(plan.stages):
        print(f"      Stage {i+1}: {list(stage)}")
    print(f"    Skipped: {list(plan.skip)}")
    print()

    # Create plan with tight deadline
    print("  Plan with tight deadline (800ms):")
    tight_constraints = SchedulingConstraints(
        deadline_ms=800,
        pool_limits={"web": 2, "db": 1, "compute": 1},
    )
    tight_plan = scheduler.plan(calls, tight_constraints)

    print(f"    Stages: {len(tight_plan.stages)}")
    for i, stage in enumerate(tight_plan.stages):
        print(f"      Stage {i+1}: {list(stage)}")
    print(f"    Skipped: {list(tight_plan.skip)}")
    print("    (Low-priority 'analytics' may be skipped to meet deadline)")
    print()

    # Show per-call timeouts
    if tight_plan.per_call_timeout_ms:
        print("  Per-call timeouts:")
        for call_id, timeout_ms in tight_plan.per_call_timeout_ms.items():
            print(f"    • {call_id}: {timeout_ms}ms")
    print()


# ------------------------------------------------------------------
# Demo 4: Combining All Features
# ------------------------------------------------------------------
async def demo_combined():
    print("=" * 70)
    print("Demo 4: Combining All Features - Production Runtime")
    print("=" * 70)
    print()
    print("A production setup using all features together:")
    print("  - Scoped registry with namespaced tools")
    print("  - Pattern-based bulkheads")
    print("  - SchedulerPolicy for planning")
    print("  - Return order control")
    print()

    # Create registry with namespaced tools
    registry = create_registry()
    await registry.register_tool(DatabaseReadTool, name="read", namespace="db")
    await registry.register_tool(DatabaseWriteTool, name="write", namespace="db")
    await registry.register_tool(WebFetchTool, name="fetch", namespace="web")
    await registry.register_tool(MCPNotionTool, name="search", namespace="mcp.notion")
    await registry.register_tool(MCPGitHubTool, name="issues", namespace="mcp.github")
    await registry.register_tool(FastTool, name="transform", namespace="compute")

    # Pattern-based bulkhead config
    bulkhead_config = BulkheadConfig(
        default_limit=10,
        patterns={
            "db.*": 3,           # Database pool
            "mcp.notion.*": 2,   # Notion rate limit
            "mcp.*": 5,          # General MCP
            "web.*": 4,          # Web requests
        },
        global_limit=20,
    )

    processor = ToolProcessor(
        registry=registry,
        enable_bulkhead=True,
        bulkhead_config=bulkhead_config,
    )

    # Use scheduler to plan execution
    scheduler = GreedyDagScheduler()

    calls = [
        ToolCallSpec(
            call_id="1",
            tool_name="db.read",
            args={"table": "users"},
            metadata=ToolMetadata(pool="db", priority=10),
        ),
        ToolCallSpec(
            call_id="2",
            tool_name="web.fetch",
            args={"url": "https://api.example.com"},
            metadata=ToolMetadata(pool="web", priority=10),
        ),
        ToolCallSpec(
            call_id="3",
            tool_name="compute.transform",
            depends_on=("1", "2"),
            metadata=ToolMetadata(pool="compute", priority=10),
        ),
    ]

    constraints = SchedulingConstraints(
        pool_limits={"db": 3, "web": 4, "compute": 2},
    )

    plan = scheduler.plan(calls, constraints)

    print("  Execution Plan:")
    for i, stage in enumerate(plan.stages):
        print(f"    Stage {i+1}: {list(stage)}")
    print()

    async with processor:
        # Execute with submission order for deterministic results
        print("  Executing tools (SUBMISSION order)...")

        # Convert plan to processor calls
        processor_calls = []
        for stage in plan.stages:
            for call_id in stage:
                spec = next(c for c in calls if c.call_id == call_id)
                processor_calls.append({
                    "tool": spec.tool_name,
                    "arguments": dict(spec.args),
                })

        results = await processor.process(
            processor_calls,
            return_order=ReturnOrder.SUBMISSION,
        )

        print()
        print("  Results (in submission order):")
        for r in results:
            status = "ok" if r.is_success else f"error: {r.error}"
            print(f"    • {r.tool}: {status} ({r.duration*1000:.0f}ms)")

    print()
    print("  ✓ Production runtime features working together:")
    print("    • Pattern bulkheads controlled concurrency by tool category")
    print("    • Scheduler planned DAG execution with dependencies")
    print("    • Results returned in deterministic submission order")
    print()


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
async def main():
    print()
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║         Runtime Features Demo - chuk-tool-processor                   ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    print()

    await demo_return_order()
    await demo_pattern_bulkheads()
    await demo_scheduler_policy()
    await demo_combined()

    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print()
    print("New APIs demonstrated:")
    print()
    print("  1. Return Order:")
    print("     results = await processor.process(calls, return_order='submission')")
    print("     results = await processor.process(calls, return_order='completion')")
    print()
    print("  2. Pattern-Based Bulkheads:")
    print("     config = BulkheadConfig(patterns={'db.*': 3, 'mcp.notion.*': 2})")
    print()
    print("  3. SchedulerPolicy:")
    print("     scheduler = GreedyDagScheduler()")
    print("     plan = scheduler.plan(calls, constraints)")
    print()
    print("These features enable chuk-tool-processor to act as a full tool")
    print("execution runtime with advanced scheduling and resource management.")
    print()


if __name__ == "__main__":
    asyncio.run(main())
