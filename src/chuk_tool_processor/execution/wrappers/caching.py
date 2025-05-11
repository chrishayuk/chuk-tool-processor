# chuk_tool_processor/execution/wrappers/caching.py
# chuk_tool_processor/execution/wrappers/caching.py
"""
Async-native caching wrapper for tool execution.

* **CacheInterface** – abstract async cache contract.
* **InMemoryCache** – simple, thread-safe (via ``asyncio.Lock``) cache.
* **CachingToolExecutor** – wraps *any* executor exposing
  ``await execute(calls, timeout=...)`` and transparently stores /
  retrieves results.

A `ToolResult` returned from cache gets ``cached=True`` and ``machine ==
"cache"`` so callers can easily detect hits.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel

from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult

# --------------------------------------------------------------------------- #
# Cache primitives
# --------------------------------------------------------------------------- #
class CacheEntry(BaseModel):
    tool: str
    arguments_hash: str
    result: Any
    created_at: datetime
    expires_at: Optional[datetime] = None


class CacheInterface(ABC):
    """Async key-value cache for tool results."""

    @abstractmethod
    async def get(self, tool: str, arguments_hash: str) -> Optional[Any]:
        ...

    @abstractmethod
    async def set(
        self,
        tool: str,
        arguments_hash: str,
        result: Any,
        *,
        ttl: Optional[int] = None,
    ) -> None:
        ...

    @abstractmethod
    async def invalidate(self, tool: str, arguments_hash: str | None = None) -> None:
        ...


class InMemoryCache(CacheInterface):
    """Simple per-process cache protected by a single asyncio lock."""

    def __init__(self, default_ttl: int | None = 300) -> None:
        self._cache: Dict[str, Dict[str, CacheEntry]] = {}
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()

    # ---------------------- CacheInterface impl ------------------------ #
    async def get(self, tool: str, arguments_hash: str) -> Optional[Any]:
        async with self._lock:
            entry = self._cache.get(tool, {}).get(arguments_hash)
            if not entry:
                return None
            if entry.expires_at and entry.expires_at < datetime.now():
                # prune expired entry
                del self._cache[tool][arguments_hash]
                if not self._cache[tool]:
                    del self._cache[tool]
                return None
            return entry.result

    async def set(
        self,
        tool: str,
        arguments_hash: str,
        result: Any,
        *,
        ttl: int | None = None,
    ) -> None:
        async with self._lock:
            now = datetime.now()
            expires_at = (
                now + timedelta(seconds=ttl if ttl is not None else self._default_ttl)
                if (ttl is not None or self._default_ttl is not None)
                else None
            )
            entry = CacheEntry(
                tool=tool,
                arguments_hash=arguments_hash,
                result=result,
                created_at=now,
                expires_at=expires_at,
            )
            self._cache.setdefault(tool, {})[arguments_hash] = entry

    async def invalidate(self, tool: str, arguments_hash: str | None = None) -> None:
        async with self._lock:
            if tool not in self._cache:
                return
            if arguments_hash:
                self._cache[tool].pop(arguments_hash, None)
                if not self._cache[tool]:
                    del self._cache[tool]
            else:
                del self._cache[tool]

# --------------------------------------------------------------------------- #
# Executor wrapper
# --------------------------------------------------------------------------- #
class CachingToolExecutor:
    """
    Decorates another executor with transparent result-caching.

    *Only successful* results (``error is None``) are stored.
    """

    def __init__(
        self,
        executor: Any,
        cache: CacheInterface,
        *,
        default_ttl: int | None = None,
        tool_ttls: Dict[str, int] | None = None,
        cacheable_tools: List[str] | None = None,
    ) -> None:
        self.executor = executor
        self.cache = cache
        self.default_ttl = default_ttl
        self.tool_ttls = tool_ttls or {}
        self.cacheable_tools = set(cacheable_tools) if cacheable_tools else None

    # ---------------------------- helpers ----------------------------- #
    @staticmethod
    def _hash_arguments(arguments: Dict[str, Any]) -> str:
        return hashlib.md5(json.dumps(arguments, sort_keys=True).encode()).hexdigest()

    def _is_cacheable(self, tool: str) -> bool:
        return self.cacheable_tools is None or tool in self.cacheable_tools

    def _ttl_for(self, tool: str) -> int | None:
        return self.tool_ttls.get(tool, self.default_ttl)

    # ------------------------------ API ------------------------------- #
    async def execute(
        self,
        calls: List[ToolCall],
        *,
        timeout: float | None = None,
        use_cache: bool = True,
    ) -> List[ToolResult]:
        # ------------------------------------------------------------------
        # 1. Split calls into cached / uncached buckets
        # ------------------------------------------------------------------
        cached_hits: List[Tuple[int, ToolResult]] = []
        uncached: List[Tuple[int, ToolCall]] = []

        if use_cache:
            for idx, call in enumerate(calls):
                if not self._is_cacheable(call.tool):
                    uncached.append((idx, call))
                    continue
                h = self._hash_arguments(call.arguments)
                cached_val = await self.cache.get(call.tool, h)
                if cached_val is None:
                    uncached.append((idx, call))
                else:
                    now = datetime.now()
                    cached_hits.append(
                        (
                            idx,
                            ToolResult(
                                tool=call.tool,
                                result=cached_val,
                                error=None,
                                start_time=now,
                                end_time=now,
                                machine="cache",
                                pid=0,
                                cached=True,
                            ),
                        )
                    )
        else:
            uncached = list(enumerate(calls))

        # Early-exit if every call was served from cache
        if not uncached:
            return [res for _, res in sorted(cached_hits, key=lambda t: t[0])]

        # ------------------------------------------------------------------
        # 2. Execute remaining calls via wrapped executor
        # ------------------------------------------------------------------
        uncached_results = await self.executor.execute(
            [call for _, call in uncached], timeout=timeout
        )

        # ------------------------------------------------------------------
        # 3. Insert fresh results into cache
        # ------------------------------------------------------------------
        if use_cache:
            for (idx, call), result in zip(uncached, uncached_results):
                if (
                    result.error is None
                    and self._is_cacheable(call.tool)
                ):
                    ttl = self._ttl_for(call.tool)
                    await self.cache.set(
                        call.tool,
                        self._hash_arguments(call.arguments),
                        result.result,
                        ttl=ttl,
                    )
                # flag as non-cached so callers can tell
                result.cached = False

        # ------------------------------------------------------------------
        # 4. Merge cached-hits + fresh results in original order
        # ------------------------------------------------------------------
        merged: List[Optional[ToolResult]] = [None] * len(calls)
        for idx, hit in cached_hits:
            merged[idx] = hit
        for (idx, _), fresh in zip(uncached, uncached_results):
            merged[idx] = fresh

        # If calls was empty, merged remains []
        return merged  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# Convenience decorators
# --------------------------------------------------------------------------- #
def cacheable(ttl: int | None = None):
    """Mark a Tool class as cacheable (optionally override TTL)."""

    def decorator(cls):
        cls._cacheable = True  # runtime flag picked up by higher-level code
        if ttl is not None:
            cls._cache_ttl = ttl
        return cls

    return decorator


def invalidate_cache(tool: str, arguments: Dict[str, Any] | None = None):
    """
    Helper that returns an *async* function which, when called with a cache
    instance, invalidates corresponding entries.
    """

    async def _invalidate(cache: CacheInterface):
        if arguments is not None:
            h = hashlib.md5(json.dumps(arguments, sort_keys=True).encode()).hexdigest()
            await cache.invalidate(tool, h)
        else:
            await cache.invalidate(tool)

    return _invalidate
