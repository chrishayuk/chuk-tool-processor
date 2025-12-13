# chuk_tool_processor/execution/bulkhead.py
"""
Bulkhead pattern implementation for tool execution isolation.

Bulkheads provide per-tool and per-namespace concurrency limits to prevent
one noisy/slow tool from starving others. This is a critical production
pattern for multi-tenant systems and mixed-criticality workloads.

Features:
- Per-tool semaphores (limit concurrent executions of specific tools)
- Per-namespace pools (limit concurrent executions across tool groups)
- Global fallback limits
- Queue depth monitoring for backpressure
- Timeout-aware acquisition

Example:
    >>> config = BulkheadConfig(
    ...     default_limit=10,
    ...     tool_limits={"slow_api": 2, "fast_cache": 50},
    ...     namespace_limits={"external": 5, "internal": 20},
    ... )
    >>> bulkhead = Bulkhead(config)
    >>>
    >>> async with bulkhead.acquire("slow_api", namespace="external"):
    ...     # Only 2 concurrent slow_api calls allowed
    ...     # Only 5 concurrent calls to any tool in "external" namespace
    ...     result = await execute_tool()
"""

from __future__ import annotations

import asyncio
import fnmatch
from collections import defaultdict
from contextlib import asynccontextmanager
from enum import Enum
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from chuk_tool_processor.logging import get_logger

logger = get_logger("chuk_tool_processor.execution.bulkhead")


class BulkheadLimitType(str, Enum):
    """Types of bulkhead limits that can be exceeded."""

    TOOL = "tool"
    NAMESPACE = "namespace"
    GLOBAL = "global"


class BulkheadConfig(BaseModel):
    """
    Configuration for bulkhead concurrency limits.

    Supports both exact tool names and glob patterns for flexible configuration.

    Attributes:
        default_limit: Default concurrency limit for tools without explicit config
        tool_limits: Per-tool concurrency limits (tool_name -> max_concurrent)
        patterns: Pattern-based limits using glob syntax (e.g., "web.*": 10, "mcp.notion.*": 2)
        namespace_limits: Per-namespace concurrency limits (namespace -> max_concurrent)
        global_limit: Optional global limit across all tools (None = unlimited)
        acquisition_timeout: Timeout for acquiring a slot (None = wait forever)
        enable_metrics: Whether to emit metrics for bulkhead operations

    Example:
        >>> config = BulkheadConfig(
        ...     default_limit=10,
        ...     tool_limits={"slow_api": 2},          # Exact match
        ...     patterns={
        ...         "web.*": 10,                       # All web.* tools
        ...         "db.*": 4,                         # All db.* tools
        ...         "mcp.notion.*": 2,                 # All mcp.notion.* tools
        ...     },
        ...     global_limit=50,
        ... )
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_default=True,
    )

    default_limit: int = Field(
        default=10,
        ge=1,
        description="Default concurrency limit for tools without explicit config",
    )
    tool_limits: dict[str, int] = Field(
        default_factory=dict,
        description="Per-tool concurrency limits (tool_name -> max_concurrent)",
    )
    patterns: dict[str, int] = Field(
        default_factory=dict,
        description="Pattern-based limits using glob syntax (pattern -> max_concurrent)",
    )
    namespace_limits: dict[str, int] = Field(
        default_factory=dict,
        description="Per-namespace concurrency limits (namespace -> max_concurrent)",
    )
    global_limit: int | None = Field(
        default=None,
        ge=1,
        description="Optional global limit across all tools (None = unlimited)",
    )
    acquisition_timeout: float | None = Field(
        default=None,
        ge=0,
        description="Timeout for acquiring a slot in seconds (None = wait forever)",
    )
    enable_metrics: bool = Field(
        default=True,
        description="Whether to emit metrics for bulkhead operations",
    )


class BulkheadStats(BaseModel):
    """Statistics for bulkhead operations."""

    model_config = ConfigDict(extra="forbid")

    tool: str = Field(description="Tool name")
    namespace: str = Field(description="Namespace name")
    acquired: int = Field(default=0, ge=0, description="Total acquisitions")
    released: int = Field(default=0, ge=0, description="Total releases")
    rejected: int = Field(default=0, ge=0, description="Total rejections")
    timeouts: int = Field(default=0, ge=0, description="Total timeout failures")
    current_active: int = Field(default=0, ge=0, description="Currently active executions")
    peak_active: int = Field(default=0, ge=0, description="Peak concurrent executions")
    total_wait_time: float = Field(default=0.0, ge=0, description="Total time spent waiting")


class BulkheadFullError(Exception):
    """Raised when a bulkhead cannot acquire a slot within timeout."""

    def __init__(
        self,
        tool: str,
        namespace: str,
        limit_type: BulkheadLimitType,
        limit: int,
        timeout: float | None = None,
    ):
        self.tool = tool
        self.namespace = namespace
        self.limit_type = limit_type
        self.limit = limit
        self.timeout = timeout

        msg = f"Bulkhead full for {tool} ({limit_type.value} limit: {limit})"
        if timeout:
            msg += f" after {timeout}s timeout"
        super().__init__(msg)


class Bulkhead:
    """
    Bulkhead implementation for concurrency isolation.

    Provides three levels of concurrency control:
    1. Per-tool limits (most specific)
    2. Per-namespace limits (group-level)
    3. Global limit (system-wide)

    All three are enforced simultaneously - a request must acquire
    slots at all applicable levels.
    """

    def __init__(self, config: BulkheadConfig | None = None):
        """
        Initialize the bulkhead.

        Args:
            config: Bulkhead configuration. If None, uses defaults.
        """
        self.config = config or BulkheadConfig()

        # Per-tool semaphores (lazily created)
        self._tool_semaphores: dict[str, asyncio.Semaphore] = {}
        self._tool_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

        # Per-namespace semaphores (lazily created)
        self._namespace_semaphores: dict[str, asyncio.Semaphore] = {}
        self._namespace_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

        # Global semaphore (created if configured)
        self._global_semaphore: asyncio.Semaphore | None = None
        if self.config.global_limit:
            self._global_semaphore = asyncio.Semaphore(self.config.global_limit)

        # Statistics tracking (mutable, so we use a dict of mutable copies)
        self._stats: dict[str, dict[str, Any]] = {}
        self._stats_lock = asyncio.Lock()

        logger.debug(
            "Bulkhead initialized: default=%d, tools=%s, namespaces=%s, global=%s",
            self.config.default_limit,
            self.config.tool_limits,
            self.config.namespace_limits,
            self.config.global_limit,
        )

    def _get_limit_for_tool(self, tool: str) -> int:
        """
        Get the concurrency limit for a tool, checking in order:
        1. Exact tool_limits match
        2. Pattern match (first matching pattern wins)
        3. Default limit

        Args:
            tool: Tool name (may include namespace prefix like "mcp.notion.search")

        Returns:
            Concurrency limit for the tool
        """
        # 1. Check exact match first
        if tool in self.config.tool_limits:
            return self.config.tool_limits[tool]

        # 2. Check patterns (use cached pattern matching)
        for pattern, limit in self.config.patterns.items():
            if self._match_pattern(pattern, tool):
                return limit

        # 3. Fall back to default
        return self.config.default_limit

    @staticmethod
    @lru_cache(maxsize=1024)
    def _match_pattern(pattern: str, tool: str) -> bool:
        """
        Check if a tool name matches a glob pattern.

        Supports:
        - "*" matches any sequence of characters
        - "?" matches any single character
        - "web.*" matches "web.api", "web.cache", etc.
        - "mcp.notion.*" matches "mcp.notion.search", "mcp.notion.create_page", etc.

        Args:
            pattern: Glob pattern (e.g., "web.*", "db.*", "mcp.notion.*")
            tool: Tool name to match

        Returns:
            True if tool matches pattern
        """
        return fnmatch.fnmatch(tool, pattern)

    async def _get_tool_semaphore(self, tool: str) -> asyncio.Semaphore:
        """Get or create a semaphore for a specific tool."""
        if tool not in self._tool_semaphores:
            async with self._tool_locks[tool]:
                if tool not in self._tool_semaphores:
                    limit = self._get_limit_for_tool(tool)
                    self._tool_semaphores[tool] = asyncio.Semaphore(limit)
                    logger.debug("Created tool semaphore: %s (limit=%d)", tool, limit)
        return self._tool_semaphores[tool]

    async def _get_namespace_semaphore(self, namespace: str) -> asyncio.Semaphore | None:
        """Get or create a semaphore for a namespace (if configured)."""
        if namespace not in self.config.namespace_limits:
            return None

        if namespace not in self._namespace_semaphores:
            async with self._namespace_locks[namespace]:
                if namespace not in self._namespace_semaphores:
                    limit = self.config.namespace_limits[namespace]
                    self._namespace_semaphores[namespace] = asyncio.Semaphore(limit)
                    logger.debug("Created namespace semaphore: %s (limit=%d)", namespace, limit)
        return self._namespace_semaphores[namespace]

    def _stats_key(self, tool: str, namespace: str) -> str:
        """Generate a key for stats tracking."""
        return f"{namespace}.{tool}"

    async def _get_stats_dict(self, tool: str, namespace: str) -> dict[str, Any]:
        """Get or create mutable stats dict for a tool/namespace combination."""
        key = self._stats_key(tool, namespace)
        if key not in self._stats:
            async with self._stats_lock:
                if key not in self._stats:
                    self._stats[key] = {
                        "tool": tool,
                        "namespace": namespace,
                        "acquired": 0,
                        "released": 0,
                        "rejected": 0,
                        "timeouts": 0,
                        "current_active": 0,
                        "peak_active": 0,
                        "total_wait_time": 0.0,
                    }
        return self._stats[key]

    @asynccontextmanager
    async def acquire(
        self,
        tool: str,
        namespace: str = "default",
        timeout: float | None = None,
    ) -> Any:
        """
        Acquire bulkhead slots for a tool execution.

        This acquires slots at all applicable levels (tool, namespace, global)
        and releases them when the context exits.

        Args:
            tool: Name of the tool to execute
            namespace: Namespace of the tool
            timeout: Override acquisition timeout (None = use config default)

        Yields:
            None (context manager for slot acquisition)

        Raises:
            BulkheadFullError: If slots cannot be acquired within timeout

        Example:
            >>> async with bulkhead.acquire("my_tool", "my_namespace"):
            ...     result = await execute_tool()
        """
        effective_timeout = timeout if timeout is not None else self.config.acquisition_timeout

        # Get all applicable semaphores
        tool_sem = await self._get_tool_semaphore(tool)
        namespace_sem = await self._get_namespace_semaphore(namespace)

        # Track stats
        stats = await self._get_stats_dict(tool, namespace)
        start_time = asyncio.get_event_loop().time()

        # Acquire all semaphores (order: global -> namespace -> tool)
        acquired: list[asyncio.Semaphore] = []

        try:
            # Global semaphore (if configured)
            if self._global_semaphore:
                try:
                    if effective_timeout:
                        await asyncio.wait_for(
                            self._global_semaphore.acquire(),
                            timeout=effective_timeout,
                        )
                    else:
                        await self._global_semaphore.acquire()
                    acquired.append(self._global_semaphore)
                except TimeoutError:
                    stats["timeouts"] += 1
                    raise BulkheadFullError(
                        tool=tool,
                        namespace=namespace,
                        limit_type=BulkheadLimitType.GLOBAL,
                        limit=self.config.global_limit or 0,
                        timeout=effective_timeout,
                    )

            # Namespace semaphore (if configured)
            if namespace_sem:
                remaining_timeout = None
                if effective_timeout:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    remaining_timeout = max(0, effective_timeout - elapsed)

                try:
                    if remaining_timeout is not None:
                        await asyncio.wait_for(
                            namespace_sem.acquire(),
                            timeout=remaining_timeout,
                        )
                    else:
                        await namespace_sem.acquire()
                    acquired.append(namespace_sem)
                except TimeoutError:
                    stats["timeouts"] += 1
                    raise BulkheadFullError(
                        tool=tool,
                        namespace=namespace,
                        limit_type=BulkheadLimitType.NAMESPACE,
                        limit=self.config.namespace_limits.get(namespace, 0),
                        timeout=effective_timeout,
                    )

            # Tool semaphore (always)
            remaining_timeout = None
            if effective_timeout:
                elapsed = asyncio.get_event_loop().time() - start_time
                remaining_timeout = max(0, effective_timeout - elapsed)

            try:
                if remaining_timeout is not None:
                    await asyncio.wait_for(
                        tool_sem.acquire(),
                        timeout=remaining_timeout,
                    )
                else:
                    await tool_sem.acquire()
                acquired.append(tool_sem)
            except TimeoutError:
                stats["timeouts"] += 1
                raise BulkheadFullError(
                    tool=tool,
                    namespace=namespace,
                    limit_type=BulkheadLimitType.TOOL,
                    limit=self.config.tool_limits.get(tool, self.config.default_limit),
                    timeout=effective_timeout,
                )

            # Update stats
            wait_time = asyncio.get_event_loop().time() - start_time
            stats["acquired"] += 1
            stats["current_active"] += 1
            stats["peak_active"] = max(stats["peak_active"], stats["current_active"])
            stats["total_wait_time"] += wait_time

            logger.debug(
                "Bulkhead acquired for %s.%s (active=%d, wait=%.3fs)",
                namespace,
                tool,
                stats["current_active"],
                wait_time,
            )

            yield

        finally:
            # Release all acquired semaphores in reverse order
            for sem in reversed(acquired):
                sem.release()

            if acquired:
                stats["released"] += 1
                stats["current_active"] -= 1
                logger.debug(
                    "Bulkhead released for %s.%s (active=%d)",
                    namespace,
                    tool,
                    stats["current_active"],
                )

    def get_tool_limit(self, tool: str) -> int:
        """Get the concurrency limit for a specific tool (supports patterns)."""
        return self._get_limit_for_tool(tool)

    def get_namespace_limit(self, namespace: str) -> int | None:
        """Get the concurrency limit for a namespace (None if not configured)."""
        return self.config.namespace_limits.get(namespace)

    def get_stats(self, tool: str, namespace: str = "default") -> BulkheadStats | None:
        """Get statistics for a tool/namespace combination as a Pydantic model."""
        key = self._stats_key(tool, namespace)
        stats_dict = self._stats.get(key)
        if stats_dict is None:
            return None
        return BulkheadStats(**stats_dict)

    def get_all_stats(self) -> dict[str, BulkheadStats]:
        """Get all bulkhead statistics as Pydantic models."""
        return {key: BulkheadStats(**stats) for key, stats in self._stats.items()}

    async def get_queue_depth(self, tool: str) -> int:
        """
        Get the approximate queue depth for a tool.

        This is the number of waiters blocked on the tool's semaphore.
        Useful for backpressure signaling.

        Args:
            tool: Tool name to check

        Returns:
            Number of waiting coroutines (approximate)
        """
        if tool not in self._tool_semaphores:
            return 0

        sem = self._tool_semaphores[tool]
        limit = self.config.tool_limits.get(tool, self.config.default_limit)

        # Queue depth = limit - available slots
        # Note: This is approximate as _value isn't guaranteed to be accurate
        # under high concurrency, but it's useful for monitoring
        return max(0, limit - sem._value)

    def configure_tool(self, tool: str, limit: int) -> None:
        """
        Configure or update the concurrency limit for a tool.

        Note: Changes only affect new semaphores. Existing semaphores
        are not modified to avoid deadlocks.

        Args:
            tool: Tool name
            limit: New concurrency limit
        """
        # Create new config with updated tool_limits
        new_tool_limits = dict(self.config.tool_limits)
        new_tool_limits[tool] = limit
        self.config = self.config.model_copy(update={"tool_limits": new_tool_limits})
        # Remove cached semaphore so it's recreated with new limit
        self._tool_semaphores.pop(tool, None)
        logger.info("Updated tool limit: %s -> %d", tool, limit)

    def configure_namespace(self, namespace: str, limit: int) -> None:
        """
        Configure or update the concurrency limit for a namespace.

        Args:
            namespace: Namespace name
            limit: New concurrency limit
        """
        new_namespace_limits = dict(self.config.namespace_limits)
        new_namespace_limits[namespace] = limit
        self.config = self.config.model_copy(update={"namespace_limits": new_namespace_limits})
        self._namespace_semaphores.pop(namespace, None)
        logger.info("Updated namespace limit: %s -> %d", namespace, limit)
