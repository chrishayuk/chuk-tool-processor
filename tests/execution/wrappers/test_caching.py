import pytest
import asyncio
import time
import hashlib
import json

from chuk_tool_processor.execution.wrappers.caching import InMemoryCache, CachingToolExecutor
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult


def hash_args(arguments: dict) -> str:
    """
    Helper to compute argument hash.
    """
    serialized = json.dumps(arguments, sort_keys=True)
    return hashlib.md5(serialized.encode()).hexdigest()

@pytest.mark.asyncio
async def test_inmemorycache_set_get_and_expiration():
    cache = InMemoryCache(default_ttl=1)
    args = {'x': 42, 'y': 'a'}
    h = hash_args(args)

    # Initially empty
    assert await cache.get('tool1', h) is None

    # Set with ttl=1 second
    await cache.set('tool1', h, 'result1', ttl=1)
    assert await cache.get('tool1', h) == 'result1'

    # After expiration
    time.sleep(1.1)
    assert await cache.get('tool1', h) is None

@pytest.mark.asyncio
async def test_inmemorycache_invalidate_specific_and_all():
    cache = InMemoryCache(default_ttl=10)
    args = {'k': 'v'}
    h = hash_args(args)

    # Set and invalidate specific
    await cache.set('tool2', h, 123)
    assert await cache.get('tool2', h) == 123
    await cache.invalidate('tool2', h)
    assert await cache.get('tool2', h) is None

    # Set again and invalidate all
    await cache.set('tool2', h, 456)
    assert await cache.get('tool2', h) == 456
    await cache.invalidate('tool2')
    assert await cache.get('tool2', h) is None

class DummyExecutor:
    """Dummy executor to track calls and return predictable results."""
    def __init__(self):
        self.called = []

    async def execute(self, calls, timeout=None):
        self.called.append(list(calls))
        # Return a ToolResult per call, echoing arguments
        return [ToolResult(tool=call.tool, result=call.arguments) for call in calls]

@pytest.mark.asyncio
async def test_caching_tool_executor_caches_and_marks():
    dummy = DummyExecutor()
    cache = InMemoryCache(default_ttl=10)
    wrapper = CachingToolExecutor(
        executor=dummy,
        cache=cache,
        default_ttl=5
    )

    call = ToolCall(tool='t1', arguments={'v': 1})

    # First execution: miss, goes to dummy
    results1 = await wrapper.execute([call])
    assert len(dummy.called) == 1
    assert results1[0].result == {'v': 1}
    # Uncached should be marked cached=False
    assert hasattr(results1[0], 'cached') and results1[0].cached is False

    # Second execution: should hit cache, no new dummy call
    results2 = await wrapper.execute([call])
    assert len(dummy.called) == 1  # no new call
    assert results2[0].result == {'v': 1}
    assert results2[0].cached is True

@pytest.mark.asyncio
async def test_caching_tool_executor_with_non_cacheable_tools():
    dummy = DummyExecutor()
    cache = InMemoryCache(default_ttl=10)
    # Only 'other' is cacheable
    wrapper = CachingToolExecutor(
        executor=dummy,
        cache=cache,
        default_ttl=5,
        cacheable_tools=['other']
    )

    call = ToolCall(tool='t3', arguments={'val': 3})

    # Execute twice: both should go to dummy
    res1 = await wrapper.execute([call])
    res2 = await wrapper.execute([call])
    assert len(dummy.called) == 2
    # Both marked uncached
    assert res1[0].cached is False
    assert res2[0].cached is False

@pytest.mark.asyncio
async def test_caching_tool_executor_respects_tool_ttls():
    dummy = DummyExecutor()
    cache = InMemoryCache(default_ttl=10)
    # ttl=1 for t1, default 10
    wrapper = CachingToolExecutor(
        executor=dummy,
        cache=cache,
        default_ttl=10,
        tool_ttls={'t1': 1}
    )

    call = ToolCall(tool='t1', arguments={'n': 5})

    # First call caches
    _ = await wrapper.execute([call])
    assert len(dummy.called) == 1

    # Immediately hit cache
    _ = await wrapper.execute([call])
    assert len(dummy.called) == 1

    # After ttl expires
    time.sleep(1.1)
    _ = await wrapper.execute([call])
    assert len(dummy.called) == 2
