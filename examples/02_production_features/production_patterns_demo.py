#!/usr/bin/env python
"""
Production Patterns Demo - Scoped Registries, Bulkheads, and ExecutionContext

This example demonstrates three critical production patterns:

1. **Scoped Registries** - Isolated tool registries for multi-tenant apps and testing
2. **Bulkheads** - Per-tool/namespace concurrency limits to prevent resource starvation
3. **ExecutionContext** - Request-scoped metadata propagation (user, tenant, tracing)

These patterns work together to build reliable, observable, multi-tenant tool systems.

Running the demo:
    python examples/02_production_features/production_patterns_demo.py
"""

import asyncio

from chuk_tool_processor import (
    # Bulkhead
    BulkheadConfig,
    # ExecutionContext
    ExecutionContext,
    # Scoped registry
    ToolProcessor,
    create_registry,
    get_current_context,
)


# ------------------------------------------------------------------
# Example tools for demonstration
# ------------------------------------------------------------------
class FastTool:
    """A fast tool that completes quickly."""

    async def execute(self, message: str = "hello") -> dict:
        await asyncio.sleep(0.01)  # Very fast
        return {"response": f"Fast: {message}"}


class SlowExternalAPI:
    """Simulates a slow external API call."""

    async def execute(self, query: str = "") -> dict:
        # Check if we have context
        ctx = get_current_context()
        user = ctx.user_id if ctx else "anonymous"

        await asyncio.sleep(0.5)  # Simulate slow API
        return {"response": f"Slow API result for '{query}'", "user": user}


class DatabaseTool:
    """Simulates database operations."""

    async def execute(self, query: str = "SELECT 1") -> dict:
        ctx = get_current_context()
        tenant = ctx.tenant_id if ctx else "default"

        await asyncio.sleep(0.1)  # Simulate DB query
        return {"result": f"DB result for tenant {tenant}", "query": query}


# ------------------------------------------------------------------
# Demo 1: Scoped Registries for Multi-Tenant Isolation
# ------------------------------------------------------------------
async def demo_scoped_registries():
    print("=" * 70)
    print("Demo 1: Scoped Registries for Multi-Tenant Isolation")
    print("=" * 70)
    print()
    print("Each tenant gets their own isolated registry with tenant-specific tools.")
    print()

    # Create isolated registries for different tenants
    tenant_a_registry = create_registry()
    tenant_b_registry = create_registry()

    # Tenant A only gets FastTool and DatabaseTool
    await tenant_a_registry.register_tool(FastTool, name="fast_tool")
    await tenant_a_registry.register_tool(DatabaseTool, name="database")

    # Tenant B gets all tools including the slow external API
    await tenant_b_registry.register_tool(FastTool, name="fast_tool")
    await tenant_b_registry.register_tool(DatabaseTool, name="database")
    await tenant_b_registry.register_tool(SlowExternalAPI, name="external_api")

    # Create processors for each tenant
    processor_a = ToolProcessor(registry=tenant_a_registry)
    processor_b = ToolProcessor(registry=tenant_b_registry)

    await processor_a.initialize()
    await processor_b.initialize()

    # Show what each tenant can access
    tools_a = await processor_a.list_tools()
    tools_b = await processor_b.list_tools()

    print(f"  Tenant A tools: {sorted(tools_a)}")
    print(f"  Tenant B tools: {sorted(tools_b)}")
    print()

    # Tenant A cannot access external_api
    print("  Tenant A calling 'fast_tool'...")
    result = await processor_a.process(
        [{"tool": "fast_tool", "arguments": {"message": "from tenant A"}}]
    )
    print(f"    ✓ Result: {result[0].result}")

    print()
    print("  Tenant B calling 'external_api' (only available to them)...")
    result = await processor_b.process(
        [{"tool": "external_api", "arguments": {"query": "search term"}}]
    )
    print(f"    ✓ Result: {result[0].result}")

    print()


# ------------------------------------------------------------------
# Demo 2: Bulkheads for Concurrency Isolation
# ------------------------------------------------------------------
async def demo_bulkheads():
    print("=" * 70)
    print("Demo 2: Bulkheads for Concurrency Isolation")
    print("=" * 70)
    print()
    print("Bulkheads prevent slow tools from starving fast ones.")
    print("We'll limit 'slow_api' to 2 concurrent calls.")
    print()

    from chuk_tool_processor import Bulkhead

    # Configure bulkhead with per-tool limits
    bulkhead_config = BulkheadConfig(
        default_limit=10,  # Default: 10 concurrent calls per tool
        tool_limits={
            "slow_api": 2,  # Limit slow API to 2 concurrent calls
            "fast_tool": 10,  # Fast tool can have 10 concurrent
        },
        global_limit=20,  # No more than 20 total concurrent calls
        acquisition_timeout=5.0,  # Wait up to 5s for a slot
    )

    bulkhead = Bulkhead(bulkhead_config)

    print("  Configuration:")
    print(f"    • slow_api limit: {bulkhead_config.tool_limits.get('slow_api', 'default')}")
    print(f"    • fast_tool limit: {bulkhead_config.tool_limits.get('fast_tool', 'default')}")
    print(f"    • global limit: {bulkhead_config.global_limit}")
    print()

    # Simulate slow API calls with bulkhead protection
    async def call_slow_api_with_bulkhead(query: str) -> dict:
        async with bulkhead.acquire("slow_api"):
            # This is where the actual tool call would happen
            await asyncio.sleep(0.5)  # Simulate slow API
            return {"response": f"Result for '{query}'"}

    # Launch many concurrent slow calls - only 2 run at once due to bulkhead
    print("  Launching 4 concurrent 'slow_api' calls (limited to 2 concurrent)...")
    print("    (The 3rd and 4th will wait for slots to become available)")

    start = asyncio.get_event_loop().time()
    slow_tasks = [
        call_slow_api_with_bulkhead(f"query-{i}")
        for i in range(4)
    ]
    await asyncio.gather(*slow_tasks)
    elapsed = asyncio.get_event_loop().time() - start

    print(f"    ✓ All 4 slow calls completed in {elapsed:.2f}s")
    print("    (With limit=2 and 0.5s/call, expected ~1.0s for 4 calls)")

    # Show bulkhead stats
    stats = bulkhead.get_stats("slow_api", "default")
    if stats:
        print()
        print("  Bulkhead stats for 'slow_api':")
        print(f"    • Total acquired: {stats.acquired}")
        print(f"    • Peak concurrent: {stats.peak_active}")
        print(f"    • Total wait time: {stats.total_wait_time:.3f}s")

    print()


# ------------------------------------------------------------------
# Demo 3: ExecutionContext for Request Tracing
# ------------------------------------------------------------------
async def demo_execution_context():
    print("=" * 70)
    print("Demo 3: ExecutionContext for Request Tracing")
    print("=" * 70)
    print()
    print("ExecutionContext carries request metadata through the entire pipeline.")
    print()

    registry = create_registry()
    await registry.register_tool(DatabaseTool, name="database")
    await registry.register_tool(SlowExternalAPI, name="external_api")

    processor = ToolProcessor(registry=registry)

    async with processor:
        # Create context with user/tenant info and deadline
        ctx = ExecutionContext(
            request_id="req-12345",
            user_id="user-alice",
            tenant_id="acme-corp",
            traceparent="00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
            budget=100.0,  # Abstract budget units
        )

        print("  Created ExecutionContext:")
        print(f"    • request_id: {ctx.request_id}")
        print(f"    • user_id: {ctx.user_id}")
        print(f"    • tenant_id: {ctx.tenant_id}")
        print(f"    • traceparent: {ctx.traceparent[:40]}...")
        print(f"    • budget: {ctx.budget}")
        print()

        # Process with context - tools can access it via get_current_context()
        print("  Calling 'database' with context...")
        result = await processor.process(
            [{"tool": "database", "arguments": {"query": "SELECT * FROM users"}}],
            context=ctx,
        )
        print(f"    ✓ Result: {result[0].result}")
        print()

        # Context with deadline
        print("  Creating context with 30-second deadline...")
        ctx_with_deadline = ExecutionContext.with_deadline(
            seconds=30,
            user_id="user-bob",
            tenant_id="other-corp",
        )
        print(f"    • remaining_time: {ctx_with_deadline.remaining_time:.1f}s")
        print(f"    • is_expired: {ctx_with_deadline.is_expired}")
        print()

        # Show headers for MCP propagation
        print("  Context as HTTP headers (for MCP propagation):")
        headers = ctx.to_headers()
        for key, value in headers.items():
            print(f"    • {key}: {value}")
        print()

        # Show context dict for logging
        print("  Context as dict (for structured logging):")
        ctx_dict = ctx.to_dict()
        for key, value in list(ctx_dict.items())[:5]:  # First 5 items
            print(f"    • {key}: {value}")

    print()


# ------------------------------------------------------------------
# Demo 4: Combining All Patterns
# ------------------------------------------------------------------
async def demo_combined():
    print("=" * 70)
    print("Demo 4: Combining All Patterns - Production Setup")
    print("=" * 70)
    print()
    print("Real production system: scoped registry + bulkheads + context")
    print()

    # Production setup for a specific tenant
    tenant_id = "acme-corp"

    # 1. Create scoped registry for this tenant
    registry = create_registry()
    await registry.register_tool(FastTool, name="fast_tool")
    await registry.register_tool(SlowExternalAPI, name="slow_api")
    await registry.register_tool(DatabaseTool, name="database")

    # 2. Configure bulkheads for production
    bulkhead_config = BulkheadConfig(
        default_limit=10,
        tool_limits={"slow_api": 3},  # Rate limit external APIs
        global_limit=50,
    )

    # 3. Create processor with all features
    processor = ToolProcessor(
        registry=registry,
        enable_bulkhead=True,
        bulkhead_config=bulkhead_config,
        enable_caching=True,
        cache_ttl=300,
        enable_retries=True,
        max_retries=3,
    )

    async with processor:
        # Simulate multiple user requests with context
        async def handle_user_request(user_id: str, request_num: int):
            ctx = ExecutionContext(
                request_id=f"req-{request_num:04d}",
                user_id=user_id,
                tenant_id=tenant_id,
            )

            # Mix of tool calls
            results = await processor.process(
                [
                    {"tool": "fast_tool", "arguments": {"message": f"from {user_id}"}},
                    {"tool": "database", "arguments": {"query": f"user lookup for {user_id}"}},
                ],
                context=ctx,
            )

            return user_id, [r.result for r in results if not r.error]

        print(f"  Processing 5 concurrent user requests for tenant '{tenant_id}'...")
        print()

        tasks = [
            handle_user_request(f"user-{i}", i)
            for i in range(5)
        ]

        results = await asyncio.gather(*tasks)

        for user_id, user_results in results:
            print(f"    {user_id}: {len(user_results)} tool calls succeeded")

        print()
        print("  ✓ All requests completed with:")
        print("    • Isolated registry (tenant-specific tools)")
        print("    • Bulkhead protection (concurrency limits)")
        print("    • Request context (user/tenant tracking)")
        print("    • Caching and retries (production reliability)")

    print()


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
async def main():
    print()
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║         Production Patterns Demo - chuk-tool-processor               ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    print()

    await demo_scoped_registries()
    await demo_bulkheads()
    await demo_execution_context()
    await demo_combined()

    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print()
    print("Key APIs demonstrated:")
    print()
    print("  1. Scoped Registries:")
    print("     registry = create_registry()")
    print("     processor = ToolProcessor(registry=registry)")
    print()
    print("  2. Bulkheads:")
    print("     config = BulkheadConfig(tool_limits={'slow_api': 2})")
    print("     processor = ToolProcessor(enable_bulkhead=True, bulkhead_config=config)")
    print()
    print("  3. ExecutionContext:")
    print("     ctx = ExecutionContext(user_id='alice', tenant_id='acme')")
    print("     results = await processor.process(data, context=ctx)")
    print()
    print("These patterns combine to build production-grade tool execution systems.")
    print()


if __name__ == "__main__":
    asyncio.run(main())
