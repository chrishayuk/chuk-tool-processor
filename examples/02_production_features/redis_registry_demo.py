#!/usr/bin/env python
# examples/02_production_features/redis_registry_demo.py
"""
Demonstration of Redis-backed tool registry for distributed deployments.

This example shows how to use RedisToolRegistry for:
- Distributed state across multiple processes/machines
- Shared tool metadata across instances
- Deferred tool loading with Redis persistence
- Multi-process tool registration patterns

Requirements:
    pip install redis[hiredis]
    # or: uv add redis[hiredis]

    # Start Redis (Docker):
    docker run -d -p 6379:6379 redis:alpine

Usage:
    python examples/02_production_features/redis_registry_demo.py
"""

import asyncio
import os
import sys


# -----------------------------------------------------------------------------
# Demo Tools
# -----------------------------------------------------------------------------
class Calculator:
    """A simple calculator tool."""

    async def execute(self, operation: str, a: float, b: float) -> dict:
        """Perform a calculation."""
        ops = {
            "add": a + b,
            "subtract": a - b,
            "multiply": a * b,
            "divide": a / b if b != 0 else float("inf"),
        }
        return {"result": ops.get(operation, 0), "operation": operation}


class TextProcessor:
    """A text processing tool."""

    async def execute(self, text: str, operation: str = "upper") -> dict:
        """Process text with various operations."""
        operations = {
            "upper": text.upper(),
            "lower": text.lower(),
            "title": text.title(),
            "reverse": text[::-1],
            "length": len(text),
        }
        return {"result": operations.get(operation, text), "operation": operation}


class DataFetcher:
    """A simulated data fetcher tool."""

    async def execute(self, resource: str, limit: int = 10) -> dict:
        """Fetch simulated data."""
        await asyncio.sleep(0.1)  # Simulate network delay
        return {
            "resource": resource,
            "items": [f"{resource}_{i}" for i in range(limit)],
            "count": limit,
        }


# -----------------------------------------------------------------------------
# Demo: Basic Redis Registry Usage
# -----------------------------------------------------------------------------
async def demo_basic_usage() -> None:
    """Demonstrate basic Redis registry operations."""
    print("=" * 60)
    print("BASIC REDIS REGISTRY USAGE")
    print("=" * 60)

    from chuk_tool_processor.registry.providers.redis import create_redis_registry

    # Create registry with custom prefix (useful for multi-tenant)
    registry = await create_redis_registry(
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        key_prefix="demo",  # All keys will be prefixed with "demo:"
    )

    # Clear any existing data (for demo purposes)
    await registry.clear()

    # Register tools (instances, not classes)
    print("\n1. Registering tools...")
    await registry.register_tool(Calculator(), name="math.calculator")
    await registry.register_tool(TextProcessor(), name="text.processor")
    await registry.register_tool(DataFetcher(), name="api.fetcher")

    # List registered tools
    tools = await registry.list_tools()
    print(f"   Registered {len(tools)} tools:")
    for tool in tools:
        print(f"   - {tool.namespace}.{tool.name}")

    # List namespaces
    namespaces = await registry.list_namespaces()
    print(f"\n2. Namespaces: {namespaces}")

    # Get and execute a tool
    print("\n3. Executing tools...")
    calc = await registry.get_tool("calculator", namespace="math")
    result = await calc.execute(operation="multiply", a=7, b=8)
    print(f"   Calculator: 7 * 8 = {result['result']}")

    text = await registry.get_tool("processor", namespace="text")
    result = await text.execute(text="hello world", operation="title")
    print(f"   TextProcessor: 'hello world' -> '{result['result']}'")

    # Get tool with strict validation
    print("\n4. Strict tool retrieval (with helpful errors)...")
    try:
        await registry.get_tool_strict("nonexistent", namespace="math")
    except Exception as e:
        print(f"   Error (expected): {type(e).__name__}")
        print(f"   {str(e)[:100]}...")

    await registry.clear()
    print("\n   Registry cleared.")


# -----------------------------------------------------------------------------
# Demo: Distributed Pattern (Multi-Process Simulation)
# -----------------------------------------------------------------------------
async def demo_distributed_pattern() -> None:
    """Demonstrate distributed registry pattern."""
    print("\n" + "=" * 60)
    print("DISTRIBUTED REGISTRY PATTERN")
    print("=" * 60)

    from chuk_tool_processor.registry.providers.redis import create_redis_registry

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # Clear existing data
    registry1 = await create_redis_registry(redis_url=redis_url, key_prefix="distributed")
    await registry1.clear()

    # Simulate Process 1: Register tools
    print("\n1. Process 1 registers tools...")
    await registry1.register_tool(Calculator(), name="math.calculator")
    await registry1.register_tool(TextProcessor(), name="text.processor")

    tools1 = await registry1.list_tools()
    print(f"   Process 1 sees {len(tools1)} tools")

    # Simulate Process 2: Connect to same Redis, sees shared metadata
    print("\n2. Process 2 connects to same Redis...")
    registry2 = await create_redis_registry(redis_url=redis_url, key_prefix="distributed")

    # Process 2 also needs to register tools locally (tools are Python objects)
    # But it can see the metadata from Process 1
    tools2_metadata = await registry2.list_tools()
    print(f"   Process 2 sees metadata for {len(tools2_metadata)} tools")

    # Process 2 registers the same tools (each process needs its own instances)
    await registry2.register_tool(Calculator(), name="math.calculator")
    await registry2.register_tool(TextProcessor(), name="text.processor")

    # Now Process 2 can execute tools
    calc = await registry2.get_tool("calculator", namespace="math")
    result = await calc.execute(operation="add", a=100, b=200)
    print(f"   Process 2 executes: 100 + 200 = {result['result']}")

    # Both processes can now independently execute the same tools
    print("\n3. Both processes execute independently...")
    result1 = await (await registry1.get_tool("calculator", "math")).execute("multiply", 5, 5)
    result2 = await (await registry2.get_tool("calculator", "math")).execute("multiply", 6, 6)
    print(f"   Process 1: 5 * 5 = {result1['result']}")
    print(f"   Process 2: 6 * 6 = {result2['result']}")

    await registry1.clear()


# -----------------------------------------------------------------------------
# Demo: Deferred Loading with Redis
# -----------------------------------------------------------------------------
async def demo_deferred_loading() -> None:
    """Demonstrate deferred tool loading with Redis persistence."""
    print("\n" + "=" * 60)
    print("DEFERRED LOADING WITH REDIS")
    print("=" * 60)

    from chuk_tool_processor.registry.providers.redis import create_redis_registry

    registry = await create_redis_registry(
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        key_prefix="deferred",
    )
    await registry.clear()

    # Register a tool as deferred (won't be loaded until needed)
    # For deferred tools, we pass instances that will be stored and loaded on-demand
    print("\n1. Registering deferred tools...")
    await registry.register_tool(
        Calculator(),
        name="math.lazy_calculator",
        metadata={
            "defer_loading": True,
            "description": "A calculator that loads on-demand",
            "tags": ["math", "lazy"],
            "search_keywords": ["calculate", "arithmetic", "numbers"],
        },
    )

    await registry.register_tool(
        DataFetcher(),
        name="api.lazy_fetcher",
        metadata={
            "defer_loading": True,
            "description": "A data fetcher that loads on-demand",
            "tags": ["api", "data", "lazy"],
            "search_keywords": ["fetch", "data", "api"],
        },
    )

    # Check deferred vs active tools
    active = await registry.get_active_tools()
    deferred = await registry.get_deferred_tools()
    print(f"   Active tools: {len(active)}")
    print(f"   Deferred tools: {len(deferred)}")
    for tool in deferred:
        print(f"   - {tool.namespace}.{tool.name} (deferred)")

    # Search deferred tools
    print("\n2. Searching deferred tools...")
    results = await registry.search_deferred_tools("calculate", limit=5)
    print(f"   Found {len(results)} tools matching 'calculate':")
    for meta in results:
        print(f"   - {meta.namespace}.{meta.name}: {meta.description}")

    # Load a deferred tool on-demand
    print("\n3. Loading deferred tool on-demand...")
    calc = await registry.load_deferred_tool("lazy_calculator", namespace="math")
    result = await calc.execute(operation="add", a=10, b=20)
    print(f"   Lazy calculator loaded and executed: 10 + 20 = {result['result']}")

    # Check status after loading
    active = await registry.get_active_tools()
    deferred = await registry.get_deferred_tools()
    print("\n4. After loading:")
    print(f"   Active tools: {len(active)}")
    print(f"   Deferred tools: {len(deferred)}")

    await registry.clear()


# -----------------------------------------------------------------------------
# Demo: Integration with ToolProcessor
# -----------------------------------------------------------------------------
async def demo_with_processor() -> None:
    """Demonstrate Redis registry with ToolProcessor."""
    print("\n" + "=" * 60)
    print("REDIS REGISTRY WITH TOOLPROCESSOR")
    print("=" * 60)

    from chuk_tool_processor import ToolProcessor
    from chuk_tool_processor.registry.providers.redis import create_redis_registry

    # Create Redis registry
    registry = await create_redis_registry(
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        key_prefix="processor",
    )
    await registry.clear()

    # Register tools (instances)
    await registry.register_tool(Calculator(), name="math.calculator")
    await registry.register_tool(TextProcessor(), name="text.processor")

    # Create processor with Redis registry
    print("\n1. Creating ToolProcessor with Redis registry...")
    async with ToolProcessor(
        registry=registry,
        enable_caching=True,
        enable_retries=True,
    ) as processor:
        # Process tool calls
        print("\n2. Processing tool calls...")

        # JSON format
        result = await processor.process(
            [{"tool": "math.calculator", "arguments": {"operation": "multiply", "a": 12, "b": 12}}]
        )
        print(f"   JSON format: 12 * 12 = {result[0].result['result']}")

        # XML format (Anthropic-style)
        result = await processor.process(
            '<tool name="text.processor" args=\'{"text": "hello redis", "operation": "upper"}\'/>'
        )
        print(f"   XML format: 'hello redis' -> '{result[0].result['result']}'")

        # OpenAI format
        result = await processor.process(
            {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "math.calculator",
                            "arguments": '{"operation": "add", "a": 1000, "b": 337}',
                        },
                    }
                ]
            }
        )
        print(f"   OpenAI format: 1000 + 337 = {result[0].result['result']}")

    await registry.clear()


# -----------------------------------------------------------------------------
# Demo: Multi-Tenant Pattern
# -----------------------------------------------------------------------------
async def demo_multi_tenant() -> None:
    """Demonstrate multi-tenant isolation with key prefixes."""
    print("\n" + "=" * 60)
    print("MULTI-TENANT ISOLATION")
    print("=" * 60)

    from chuk_tool_processor.registry.providers.redis import create_redis_registry

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # Create isolated registries for different tenants
    print("\n1. Creating tenant-specific registries...")
    tenant_a = await create_redis_registry(redis_url=redis_url, key_prefix="tenant_a")
    tenant_b = await create_redis_registry(redis_url=redis_url, key_prefix="tenant_b")

    await tenant_a.clear()
    await tenant_b.clear()

    # Register different tools for each tenant (instances)
    print("\n2. Registering tenant-specific tools...")
    await tenant_a.register_tool(Calculator(), name="tools.calculator")
    await tenant_a.register_tool(TextProcessor(), name="tools.text")

    await tenant_b.register_tool(DataFetcher(), name="tools.fetcher")

    # Each tenant only sees their own tools
    tools_a = await tenant_a.list_tools()
    tools_b = await tenant_b.list_tools()

    print(f"\n3. Tenant A tools ({len(tools_a)}):")
    for tool in tools_a:
        print(f"   - {tool.namespace}.{tool.name}")

    print(f"\n   Tenant B tools ({len(tools_b)}):")
    for tool in tools_b:
        print(f"   - {tool.namespace}.{tool.name}")

    # Tenants can't access each other's tools
    print("\n4. Isolation verification...")
    calc = await tenant_a.get_tool("calculator", namespace="tools")
    fetcher = await tenant_b.get_tool("fetcher", namespace="tools")

    print(f"   Tenant A can access calculator: {calc is not None}")
    print(f"   Tenant B can access fetcher: {fetcher is not None}")

    # Cross-tenant access returns None
    cross_access = await tenant_a.get_tool("fetcher", namespace="tools")
    print(f"   Tenant A can access Tenant B's fetcher: {cross_access is not None}")

    await tenant_a.clear()
    await tenant_b.clear()


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
async def main() -> None:
    """Run all demos."""
    print("\nREDIS REGISTRY DEMO")
    print("=" * 60)

    # Check Redis connectivity
    try:
        from redis.asyncio import Redis
    except ImportError:
        print("\nError: redis package not installed.")
        print("Install with: pip install redis[hiredis]")
        print("         or: uv add redis[hiredis]")
        sys.exit(1)

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    print(f"\nConnecting to Redis: {redis_url}")

    try:
        redis_client = Redis.from_url(redis_url)
        await redis_client.ping()
        await redis_client.aclose()
        print("Redis connection successful!")
    except Exception as e:
        print(f"\nError: Cannot connect to Redis: {e}")
        print("\nMake sure Redis is running:")
        print("  docker run -d -p 6379:6379 redis:alpine")
        print("\nOr set REDIS_URL environment variable:")
        print("  export REDIS_URL=redis://your-redis-host:6379/0")
        sys.exit(1)

    # Run demos
    await demo_basic_usage()
    await demo_distributed_pattern()
    await demo_deferred_loading()
    await demo_with_processor()
    await demo_multi_tenant()

    print("\n" + "=" * 60)
    print("ALL DEMOS COMPLETED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
