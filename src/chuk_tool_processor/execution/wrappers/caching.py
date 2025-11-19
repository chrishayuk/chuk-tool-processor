# chuk_tool_processor/execution/wrappers/caching.py
"""
Async-native caching wrapper for tool execution.

This module provides:

* **CacheInterface** - abstract async cache contract for custom implementations
* **InMemoryCache** - simple, thread-safe in-memory cache with TTL support
* **CachingToolExecutor** - executor wrapper that transparently caches results

Results retrieved from cache are marked with `cached=True` and `machine="cache"`
for easy detection.
"""

from __future__ import annotations

import asyncio
import hashlib
import json as stdlib_json  # Use stdlib json for consistent hashing
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult

logger = get_logger("chuk_tool_processor.execution.wrappers.caching")

# Optional observability imports
try:
    from chuk_tool_processor.observability.metrics import get_metrics
    from chuk_tool_processor.observability.tracing import trace_cache_operation

    _observability_available = True
except ImportError:
    _observability_available = False

    # No-op functions when observability not available
    def get_metrics():
        return None

    def trace_cache_operation(*_args, **_kwargs):
        from contextlib import nullcontext

        return nullcontext()


# --------------------------------------------------------------------------- #
# Cache primitives
# --------------------------------------------------------------------------- #
class CacheEntry(BaseModel):
    """
    Model representing a cached tool result.

    Attributes:
        tool: Name of the tool
        arguments_hash: Hash of the tool arguments
        result: The cached result value
        created_at: When the entry was created
        expires_at: When the entry expires (None = no expiration)
    """

    tool: str = Field(..., description="Tool name")
    arguments_hash: str = Field(..., description="MD5 hash of arguments")
    result: Any = Field(..., description="Cached result value")
    created_at: datetime = Field(..., description="Creation timestamp")
    expires_at: datetime | None = Field(None, description="Expiration timestamp")


class CacheInterface(ABC):
    """
    Abstract interface for tool result caches.

    All cache implementations must be async-native and thread-safe.
    """

    @abstractmethod
    async def get(self, tool: str, arguments_hash: str) -> Any | None:
        """
        Get a cached result by tool name and arguments hash.

        Args:
            tool: Tool name
            arguments_hash: Hash of the arguments

        Returns:
            Cached result value or None if not found
        """
        pass

    @abstractmethod
    async def set(
        self,
        tool: str,
        arguments_hash: str,
        result: Any,
        *,
        ttl: int | None = None,
    ) -> None:
        """
        Set a cache entry.

        Args:
            tool: Tool name
            arguments_hash: Hash of the arguments
            result: Result value to cache
            ttl: Time-to-live in seconds (overrides default)
        """
        pass

    @abstractmethod
    async def invalidate(self, tool: str, arguments_hash: str | None = None) -> None:
        """
        Invalidate cache entries.

        Args:
            tool: Tool name
            arguments_hash: Optional arguments hash. If None, all entries for the tool are invalidated.
        """
        pass

    async def clear(self) -> None:
        """
        Clear all cache entries.

        Default implementation raises NotImplementedError.
        Override in subclasses to provide an efficient implementation.
        """
        raise NotImplementedError("Cache clear not implemented")

    async def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache statistics (implementation-specific)
        """
        return {"implemented": False}


class InMemoryCache(CacheInterface):
    """
    In-memory cache implementation with async thread-safety.

    This cache uses a two-level dictionary structure with asyncio locks
    to ensure thread safety. Entries can have optional TTL values.
    """

    def __init__(self, default_ttl: int | None = 300) -> None:
        """
        Initialize the in-memory cache.

        Args:
            default_ttl: Default time-to-live in seconds (None = no expiration)
        """
        self._cache: dict[str, dict[str, CacheEntry]] = {}
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()
        self._stats: dict[str, int] = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "invalidations": 0,
            "expirations": 0,
        }

        logger.debug(f"Initialized InMemoryCache with default_ttl={default_ttl}s")

    # ---------------------- Helper methods ------------------------ #
    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if an entry is expired."""
        return entry.expires_at is not None and entry.expires_at < datetime.now()

    async def _prune_expired(self) -> int:
        """
        Remove all expired entries.

        Returns:
            Number of entries removed
        """
        now = datetime.now()
        removed = 0

        async with self._lock:
            for tool in list(self._cache.keys()):
                tool_cache = self._cache[tool]
                for arg_hash in list(tool_cache.keys()):
                    entry = tool_cache[arg_hash]
                    if entry.expires_at and entry.expires_at < now:
                        del tool_cache[arg_hash]
                        removed += 1
                        self._stats["expirations"] += 1

                # Remove empty tool caches
                if not tool_cache:
                    del self._cache[tool]

        return removed

    # ---------------------- CacheInterface implementation ------------------------ #
    async def get(self, tool: str, arguments_hash: str) -> Any | None:
        """
        Get a cached result, checking expiration.

        Args:
            tool: Tool name
            arguments_hash: Hash of the arguments

        Returns:
            Cached result value or None if not found or expired
        """
        async with self._lock:
            entry = self._cache.get(tool, {}).get(arguments_hash)

            if not entry:
                self._stats["misses"] += 1
                return None

            if self._is_expired(entry):
                # Prune expired entry
                del self._cache[tool][arguments_hash]
                if not self._cache[tool]:
                    del self._cache[tool]

                self._stats["expirations"] += 1
                self._stats["misses"] += 1
                return None

            self._stats["hits"] += 1
            return entry.result

    async def set(
        self,
        tool: str,
        arguments_hash: str,
        result: Any,
        *,
        ttl: int | None = None,
    ) -> None:
        """
        Set a cache entry with optional custom TTL.

        Args:
            tool: Tool name
            arguments_hash: Hash of the arguments
            result: Result value to cache
            ttl: Time-to-live in seconds (overrides default)
        """
        async with self._lock:
            now = datetime.now()

            # Calculate expiration
            use_ttl = ttl if ttl is not None else self._default_ttl
            expires_at = now + timedelta(seconds=use_ttl) if use_ttl is not None else None

            # Create entry
            entry = CacheEntry(
                tool=tool,
                arguments_hash=arguments_hash,
                result=result,
                created_at=now,
                expires_at=expires_at,
            )

            # Store in cache
            self._cache.setdefault(tool, {})[arguments_hash] = entry
            self._stats["sets"] += 1

            logger.debug(f"Cached result for {tool} (TTL: {use_ttl if use_ttl is not None else 'none'}s)")

    async def invalidate(self, tool: str, arguments_hash: str | None = None) -> None:
        """
        Invalidate cache entries for a tool.

        Args:
            tool: Tool name
            arguments_hash: Optional arguments hash. If None, all entries for the tool are invalidated.
        """
        async with self._lock:
            if tool not in self._cache:
                return

            if arguments_hash:
                # Invalidate specific entry
                self._cache[tool].pop(arguments_hash, None)
                if not self._cache[tool]:
                    del self._cache[tool]
                self._stats["invalidations"] += 1
                logger.debug(f"Invalidated specific cache entry for {tool}")
            else:
                # Invalidate all entries for tool
                count = len(self._cache[tool])
                del self._cache[tool]
                self._stats["invalidations"] += count
                logger.debug(f"Invalidated all cache entries for {tool} ({count} entries)")

    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self._lock:
            count = sum(len(entries) for entries in self._cache.values())
            self._cache.clear()
            self._stats["invalidations"] += count
            logger.debug(f"Cleared entire cache ({count} entries)")

    async def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with hits, misses, sets, invalidations, and entry counts
        """
        async with self._lock:
            stats = dict(self._stats)
            stats["implemented"] = True
            stats["entry_count"] = sum(len(entries) for entries in self._cache.values())
            stats["tool_count"] = len(self._cache)

            # Calculate hit rate
            total_gets = stats["hits"] + stats["misses"]
            stats["hit_rate"] = stats["hits"] / total_gets if total_gets > 0 else 0.0

            return stats


# --------------------------------------------------------------------------- #
# Executor wrapper
# --------------------------------------------------------------------------- #
class CachingToolExecutor:
    """
    Executor wrapper that transparently caches successful tool results.

    This wrapper intercepts tool calls, checks if results are available in cache,
    and only executes uncached calls. Successful results are automatically stored
    in the cache for future use.
    """

    def __init__(
        self,
        executor: Any,
        cache: CacheInterface,
        *,
        default_ttl: int | None = None,
        tool_ttls: dict[str, int] | None = None,
        cacheable_tools: list[str] | None = None,
    ) -> None:
        """
        Initialize the caching executor.

        Args:
            executor: The underlying executor to wrap
            cache: Cache implementation to use
            default_ttl: Default time-to-live in seconds
            tool_ttls: Dict mapping tool names to custom TTL values
            cacheable_tools: List of tool names that should be cached. If None, all tools are cacheable.
        """
        self.executor = executor
        self.cache = cache
        self.default_ttl = default_ttl
        self.tool_ttls = tool_ttls or {}
        self.cacheable_tools = set(cacheable_tools) if cacheable_tools else None

        logger.debug(
            f"Initialized CachingToolExecutor with {len(self.tool_ttls)} custom TTLs, default TTL={default_ttl}s"
        )

    # ---------------------------- helpers ----------------------------- #
    @staticmethod
    def _hash_arguments(arguments: dict[str, Any]) -> str:
        """
        Generate a stable hash for tool arguments.

        Args:
            arguments: Tool arguments dict

        Returns:
            MD5 hash of the sorted JSON representation
        """
        try:
            # Use stdlib json for consistent hashing across orjson/stdlib
            blob = stdlib_json.dumps(arguments, sort_keys=True, default=str)
            return hashlib.md5(blob.encode(), usedforsecurity=False).hexdigest()  # nosec B324
        except Exception as e:
            logger.warning(f"Error hashing arguments: {e}")
            # Fallback to a string representation
            return hashlib.md5(str(arguments).encode(), usedforsecurity=False).hexdigest()  # nosec B324

    def _is_cacheable(self, tool: str) -> bool:
        """
        Check if a tool is cacheable.

        Args:
            tool: Tool name

        Returns:
            True if the tool should be cached, False otherwise
        """
        return self.cacheable_tools is None or tool in self.cacheable_tools

    def _ttl_for(self, tool: str) -> int | None:
        """
        Get the TTL for a specific tool.

        Args:
            tool: Tool name

        Returns:
            Tool-specific TTL or default TTL
        """
        return self.tool_ttls.get(tool, self.default_ttl)

    # ------------------------------ API ------------------------------- #
    async def execute(
        self,
        calls: list[ToolCall],
        *,
        timeout: float | None = None,
        use_cache: bool = True,
    ) -> list[ToolResult]:
        """
        Execute tool calls with caching.

        Args:
            calls: List of tool calls to execute
            timeout: Optional timeout for execution
            use_cache: Whether to use cached results

        Returns:
            List of tool results in the same order as calls
        """
        # Handle empty calls
        if not calls:
            return []

        # ------------------------------------------------------------------
        # 1. Split calls into cached / uncached buckets
        # ------------------------------------------------------------------
        cached_hits: list[tuple[int, ToolResult]] = []
        uncached: list[tuple[int, ToolCall]] = []

        if use_cache:
            for idx, call in enumerate(calls):
                if not self._is_cacheable(call.tool):
                    logger.debug(f"Tool {call.tool} is not cacheable, executing directly")
                    uncached.append((idx, call))
                    continue

                # Use idempotency_key if available, otherwise hash arguments
                # PERFORMANCE: Only compute idempotency key when caching is actually used
                cache_key = call.get_idempotency_key()

                # Trace cache lookup operation
                with trace_cache_operation("lookup", call.tool):
                    cached_val = await self.cache.get(call.tool, cache_key)

                # Record metrics
                metrics = get_metrics()
                if metrics:
                    metrics.record_cache_operation(call.tool, "lookup", hit=(cached_val is not None))

                if cached_val is None:
                    # Cache miss
                    logger.debug(f"Cache miss for {call.tool}")
                    uncached.append((idx, call))
                else:
                    # Cache hit
                    logger.debug(f"Cache hit for {call.tool}")
                    now = datetime.now(UTC)
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
            # Skip cache entirely
            logger.debug("Cache disabled for this execution")
            uncached = list(enumerate(calls))

        # Early-exit if every call was served from cache
        if not uncached:
            logger.debug(f"All {len(cached_hits)} calls served from cache")
            return [res for _, res in sorted(cached_hits, key=lambda t: t[0])]

        # ------------------------------------------------------------------
        # 2. Execute remaining calls via wrapped executor
        # ------------------------------------------------------------------
        logger.debug(f"Executing {len(uncached)} uncached calls")
        # Pass use_cache=False to avoid potential double-caching if executor also has caching
        executor_kwargs = {"timeout": timeout}
        if hasattr(self.executor, "use_cache"):
            executor_kwargs["use_cache"] = False

        uncached_results = await self.executor.execute([call for _, call in uncached], **executor_kwargs)

        # ------------------------------------------------------------------
        # 3. Insert fresh results into cache
        # ------------------------------------------------------------------
        if use_cache:
            cache_tasks = []
            metrics = get_metrics()

            for (_idx, call), result in zip(uncached, uncached_results, strict=False):
                if result.error is None and self._is_cacheable(call.tool):
                    ttl = self._ttl_for(call.tool)
                    logger.debug(f"Caching result for {call.tool} with TTL={ttl}s")

                    # Use idempotency_key if available, otherwise hash arguments
                    # PERFORMANCE: Only compute idempotency key when caching is actually used
                    cache_key = call.get_idempotency_key()

                    # Trace and record cache set operation
                    # Bind loop variables to avoid B023 error
                    async def cache_with_trace(tool=call.tool, key=cache_key, value=result.result, ttl_val=ttl):
                        with trace_cache_operation("set", tool, attributes={"ttl": ttl_val}):
                            await self.cache.set(tool, key, value, ttl=ttl_val)
                        if metrics:
                            metrics.record_cache_operation(tool, "set")

                    cache_tasks.append(cache_with_trace())

                # Flag as non-cached so callers can tell
                if hasattr(result, "cached"):
                    result.cached = False
                else:
                    # For older ToolResult objects that might not have cached attribute
                    result.cached = False

            # Wait for all cache operations to complete
            if cache_tasks:
                await asyncio.gather(*cache_tasks)

        # ------------------------------------------------------------------
        # 4. Merge cached-hits + fresh results in original order
        # ------------------------------------------------------------------
        merged: list[ToolResult | None] = [None] * len(calls)
        for idx, hit in cached_hits:
            merged[idx] = hit
        for (idx, _), fresh in zip(uncached, uncached_results, strict=False):
            merged[idx] = fresh

        # If calls was empty, merged remains []
        return [result for result in merged if result is not None]


# --------------------------------------------------------------------------- #
# Convenience decorators
# --------------------------------------------------------------------------- #
def cacheable(ttl: int | None = None):
    """
    Decorator to mark a tool class as cacheable.

    Example:
        @cacheable(ttl=600)  # Cache for 10 minutes
        class WeatherTool:
            async def execute(self, location: str) -> Dict[str, Any]:
                # Implementation

    Args:
        ttl: Optional custom time-to-live in seconds

    Returns:
        Decorated class with caching metadata
    """

    def decorator(cls):
        cls._cacheable = True  # Runtime flag picked up by higher-level code
        if ttl is not None:
            cls._cache_ttl = ttl
        return cls

    return decorator


def invalidate_cache(tool: str, arguments: dict[str, Any] | None = None):
    """
    Create an async function that invalidates specific cache entries.

    Example:
        invalidator = invalidate_cache("weather", {"location": "London"})
        await invalidator(cache)  # Call with a cache instance

    Args:
        tool: Tool name
        arguments: Optional arguments dict. If None, all entries for the tool are invalidated.

    Returns:
        Async function that takes a cache instance and invalidates entries
    """

    async def _invalidate(cache: CacheInterface):
        if arguments is not None:
            # Use stdlib json for consistent hashing across orjson/stdlib
            h = hashlib.md5(
                stdlib_json.dumps(arguments, sort_keys=True, default=str).encode(), usedforsecurity=False
            ).hexdigest()  # nosec B324
            await cache.invalidate(tool, h)
            logger.debug(f"Invalidated cache entry for {tool} with specific arguments")
        else:
            await cache.invalidate(tool)
            logger.debug(f"Invalidated all cache entries for {tool}")

    return _invalidate
