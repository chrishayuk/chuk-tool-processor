# chuk_tool_processor/execution/wrappers/rate_limiting.py
"""
Async-native rate-limiting wrapper.

Two layers of limits are enforced:

* **Global** - ``<N requests> / <period>`` over *all* tools.
* **Per-tool** - independent ``<N requests> / <period>`` windows.

A simple sliding-window algorithm with timestamp queues is used.  
`asyncio.Lock` guards shared state so the wrapper can be used safely from
multiple coroutines.
"""
from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.logging import get_logger

logger = get_logger("chuk_tool_processor.execution.wrappers.rate_limiting")

# --------------------------------------------------------------------------- #
# Core limiter
# --------------------------------------------------------------------------- #
class RateLimiter:
    """
    Async-native rate limiter for controlling execution frequency.
    
    Implements a sliding window algorithm to enforce rate limits both globally
    and per-tool. All operations are thread-safe using asyncio locks.
    """
    
    def __init__(
        self,
        *,
        global_limit: Optional[int] = None,
        global_period: float = 60.0,
        tool_limits: Optional[Dict[str, Tuple[int, float]]] = None,
    ) -> None:
        """
        Initialize the rate limiter.
        
        Args:
            global_limit: Maximum global requests per period (None = no limit)
            global_period: Time period in seconds for the global limit
            tool_limits: Dict mapping tool names to (limit, period) tuples
        """
        self.global_limit = global_limit
        self.global_period = global_period
        self.tool_limits = tool_limits or {}

        # Timestamp queues
        self._global_ts: List[float] = []
        self._tool_ts: Dict[str, List[float]] = {}

        # Locks for thread safety
        self._global_lock = asyncio.Lock()
        self._tool_locks: Dict[str, asyncio.Lock] = {}
        
        logger.debug(
            f"Initialized rate limiter: global={global_limit}/{global_period}s, "
            f"tool-specific={len(self.tool_limits)} tools"
        )

    # --------------------- helpers -------------------- #
    async def _acquire_global(self) -> None:
        """Block until a global slot is available."""
        if self.global_limit is None:
            return

        while True:
            async with self._global_lock:
                now = time.monotonic()
                cutoff = now - self.global_period
                
                # Prune expired timestamps
                self._global_ts = [t for t in self._global_ts if t > cutoff]

                # Check if we're under the limit
                if len(self._global_ts) < self.global_limit:
                    self._global_ts.append(now)
                    return

                # Calculate wait time until a slot becomes available
                wait = (self._global_ts[0] + self.global_period) - now
                
            logger.debug(f"Global rate limit reached, waiting {wait:.2f}s")
            await asyncio.sleep(wait)

    async def _acquire_tool(self, tool: str) -> None:
        """Block until a per-tool slot is available (if the tool has a limit)."""
        if tool not in self.tool_limits:
            return

        limit, period = self.tool_limits[tool]
        lock = self._tool_locks.setdefault(tool, asyncio.Lock())
        buf = self._tool_ts.setdefault(tool, [])

        while True:
            async with lock:
                now = time.monotonic()
                cutoff = now - period
                
                # Prune expired timestamps in-place
                buf[:] = [t for t in buf if t > cutoff]

                # Check if we're under the limit
                if len(buf) < limit:
                    buf.append(now)
                    return

                # Calculate wait time until a slot becomes available
                wait = (buf[0] + period) - now
                
            logger.debug(f"Tool '{tool}' rate limit reached, waiting {wait:.2f}s")
            await asyncio.sleep(wait)

    # ----------------------- public -------------------- #
    async def wait(self, tool: str) -> None:
        """
        Block until rate limits allow execution.
        
        This method blocks until both global and tool-specific rate limits
        allow one more execution of the specified tool.
        
        Args:
            tool: Name of the tool being executed
        """
        await self._acquire_global()
        await self._acquire_tool(tool)
        
    async def check_limits(self, tool: str) -> Tuple[bool, bool]:
        """
        Check if the tool would be rate limited without consuming a slot.
        
        This is a non-blocking method useful for checking limits without
        affecting the rate limiting state.
        
        Args:
            tool: Name of the tool to check
            
        Returns:
            Tuple of (global_limit_reached, tool_limit_reached)
        """
        global_limited = False
        tool_limited = False
        
        # Check global limit
        if self.global_limit is not None:
            async with self._global_lock:
                now = time.monotonic()
                cutoff = now - self.global_period
                active_ts = [t for t in self._global_ts if t > cutoff]
                global_limited = len(active_ts) >= self.global_limit
        
        # Check tool limit
        if tool in self.tool_limits:
            limit, period = self.tool_limits[tool]
            async with self._tool_locks.setdefault(tool, asyncio.Lock()):
                now = time.monotonic()
                cutoff = now - period
                buf = self._tool_ts.get(tool, [])
                active_ts = [t for t in buf if t > cutoff]
                tool_limited = len(active_ts) >= limit
                
        return global_limited, tool_limited


# --------------------------------------------------------------------------- #
# Executor wrapper
# --------------------------------------------------------------------------- #
class RateLimitedToolExecutor:
    """
    Executor wrapper that applies rate limiting to tool executions.
    
    This wrapper delegates to another executor but ensures that all
    tool calls respect the configured rate limits.
    """

    def __init__(self, executor: Any, limiter: RateLimiter) -> None:
        """
        Initialize the rate-limited executor.
        
        Args:
            executor: The underlying executor to wrap
            limiter: The RateLimiter that controls execution frequency
        """
        self.executor = executor
        self.limiter = limiter
        logger.debug(f"Initialized rate-limited executor")

    async def execute(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
        use_cache: bool = True,
    ) -> List[ToolResult]:
        """
        Execute tool calls while respecting rate limits.
        
        This method blocks until rate limits allow execution, then delegates
        to the underlying executor.
        
        Args:
            calls: List of tool calls to execute
            timeout: Optional timeout for execution
            use_cache: Whether to use cached results (forwarded to underlying executor)
            
        Returns:
            List of tool results
        """
        if not calls:
            return []
            
        # Block for each call *before* dispatching to the wrapped executor
        for c in calls:
            await self.limiter.wait(c.tool)
            
        # Check if the executor has a use_cache parameter
        if hasattr(self.executor, "execute"):
            sig = inspect.signature(self.executor.execute)
            if "use_cache" in sig.parameters:
                return await self.executor.execute(calls, timeout=timeout, use_cache=use_cache)
                
        # Fall back to standard execute method
        return await self.executor.execute(calls, timeout=timeout)


# --------------------------------------------------------------------------- #
# Convenience decorator for tools
# --------------------------------------------------------------------------- #
def rate_limited(limit: int, period: float = 60.0):
    """
    Class decorator that marks a Tool with default rate-limit metadata.
    
    This allows higher-level code to detect and configure rate limiting
    for the tool class.

    Example:
        @rate_limited(limit=10, period=60.0)
        class WeatherTool:
            async def execute(self, location: str) -> Dict[str, Any]:
                # Implementation
                
    Args:
        limit: Maximum number of calls allowed in the period
        period: Time period in seconds
        
    Returns:
        Decorated class with rate limit metadata
    """
    def decorator(cls):
        cls._rate_limit = limit
        cls._rate_period = period
        return cls

    return decorator