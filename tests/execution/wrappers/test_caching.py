# tests/execution/wrappers/test_caching.py
import asyncio
import hashlib
import json
from typing import List

import pytest

from chuk_tool_processor.execution.wrappers.caching import (
    CachingToolExecutor,
    InMemoryCache,
)
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _hash_args(arguments: dict) -> str:
    """Return the MD5 hash that the cache uses internally."""
    return hashlib.md5(json.dumps(arguments, sort_keys=True).encode()).hexdigest()


class DummyExecutor:
    """Echoes back ToolResults and records invocations."""

    def __init__(self) -> None:
        self.called: List[List[ToolCall]] = []

    async def execute(self, calls, timeout=None):
        self.called.append(list(calls))
        return [ToolResult(tool=c.tool, result=c.arguments) for c in calls]


# --------------------------------------------------------------------------- #
# In-memory cache tests
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_inmemory_set_get_and_expire():
    cache = InMemoryCache(default_ttl=1)
    args = {"x": 42}
    h = _hash_args(args)

    # empty → miss
    assert await cache.get("tool", h) is None

    await cache.set("tool", h, "res", ttl=1)
    assert await cache.get("tool", h) == "res"

    # let TTL elapse
    await asyncio.sleep(1.1)
    assert await cache.get("tool", h) is None


@pytest.mark.asyncio
async def test_inmemory_invalidate_specific_and_all():
    cache = InMemoryCache(default_ttl=10)
    args = {"k": "v"}
    h = _hash_args(args)

    await cache.set("tool2", h, 123)
    await cache.invalidate("tool2", h)
    assert await cache.get("tool2", h) is None

    await cache.set("tool2", h, 456)
    await cache.invalidate("tool2")  # wipe all
    assert await cache.get("tool2", h) is None


# --------------------------------------------------------------------------- #
# CachingToolExecutor tests
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_executor_caches_and_marks_hits():
    exec_ = DummyExecutor()
    cache = InMemoryCache(default_ttl=10)
    wrapper = CachingToolExecutor(exec_, cache, default_ttl=5)

    call = ToolCall(tool="t1", arguments={"v": 1})

    # 1st call → miss
    res1 = (await wrapper.execute([call]))[0]
    assert len(exec_.called) == 1
    assert res1.cached is False

    # 2nd call → hit
    res2 = (await wrapper.execute([call]))[0]
    assert len(exec_.called) == 1
    assert res2.cached is True


@pytest.mark.asyncio
async def test_executor_respects_cacheable_whitelist():
    exec_ = DummyExecutor()
    cache = InMemoryCache()
    wrapper = CachingToolExecutor(
        exec_, cache, default_ttl=5, cacheable_tools=["other"]
    )

    call = ToolCall(tool="t3", arguments={})

    # Not in whitelist → always uncached
    _ = await wrapper.execute([call])
    _ = await wrapper.execute([call])
    assert len(exec_.called) == 2


@pytest.mark.asyncio
async def test_executor_respects_per_tool_ttl():
    exec_ = DummyExecutor()
    cache = InMemoryCache()
    wrapper = CachingToolExecutor(exec_, cache, default_ttl=10, tool_ttls={"t1": 1})

    call = ToolCall(tool="t1", arguments={"n": 5})

    # cached
    await wrapper.execute([call])
    assert len(exec_.called) == 1

    # immediate hit
    await wrapper.execute([call])
    assert len(exec_.called) == 1

    # let per-tool TTL expire
    await asyncio.sleep(1.1)
    await wrapper.execute([call])
    assert len(exec_.called) == 2
