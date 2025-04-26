# chuk_tool_processor/execution/wrappers/rate_limiting.py
import asyncio
import time
from datetime import datetime
from typing import Dict, Optional, List, Any, Tuple

# imports
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.core.exceptions import ToolExecutionError


class RateLimiter:
    """
    Rate limiter for tool executions.
    Supports per-tool rate limits and global rate limits.
    """
    def __init__(
        self,
        global_limit: Optional[int] = None,
        global_period: float = 60.0,
        tool_limits: Optional[Dict[str, Tuple[int, float]]] = None
    ):
        """
        Initialize the rate limiter.
        """
        self.global_limit = global_limit
        self.global_period = global_period
        self.tool_limits = tool_limits or {}
        
        # Track request timestamps
        self._global_timestamps: List[float] = []
        self._tool_timestamps: Dict[str, List[float]] = {}
        
        # Locks for concurrency safety
        self._global_lock = asyncio.Lock()
        self._tool_locks: Dict[str, asyncio.Lock] = {}
    
    async def _wait_for_global_limit(self) -> None:
        """
        Wait until global rate limit allows another request.
        """
        if self.global_limit is None:
            return
        
        while True:
            # Acquire lock to check and possibly record
            async with self._global_lock:
                now = time.time()
                # Remove expired timestamps
                cutoff = now - self.global_period
                self._global_timestamps = [ts for ts in self._global_timestamps if ts > cutoff]
                # If under limit, record and proceed
                if len(self._global_timestamps) < self.global_limit:
                    self._global_timestamps.append(now)
                    return
                # Otherwise compute wait time
                oldest = min(self._global_timestamps)
                wait_time = (oldest + self.global_period) - now
            # Sleep outside lock
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            else:
                # retry immediately
                continue
    
    async def _wait_for_tool_limit(self, tool: str) -> None:
        """
        Wait until tool-specific rate limit allows another request.
        """
        # Check if tool has a limit
        if tool not in self.tool_limits:
            return
        limit, period = self.tool_limits[tool]
        
        # Initialize lock and timestamps list if needed
        if tool not in self._tool_locks:
            self._tool_locks[tool] = asyncio.Lock()
        if tool not in self._tool_timestamps:
            self._tool_timestamps[tool] = []
        
        while True:
            async with self._tool_locks[tool]:
                now = time.time()
                # Remove expired timestamps
                cutoff = now - period
                self._tool_timestamps[tool] = [ts for ts in self._tool_timestamps[tool] if ts > cutoff]
                # If under limit, record and proceed
                if len(self._tool_timestamps[tool]) < limit:
                    self._tool_timestamps[tool].append(now)
                    return
                # Otherwise compute wait time
                oldest = min(self._tool_timestamps[tool])
                wait_time = (oldest + period) - now
            # Sleep outside lock
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            else:
                continue
    
    async def wait(self, tool: str) -> None:
        """
        Wait until rate limits allow execution of the given tool.
        """
        # Wait for global limit first
        await self._wait_for_global_limit()
        # Then wait for tool-specific limit
        await self._wait_for_tool_limit(tool)


class RateLimitedToolExecutor:
    """
    Wrapper for a tool executor that applies rate limiting.
    """
    def __init__(
        self,
        executor: Any,
        rate_limiter: RateLimiter
    ):
        """
        Initialize the rate-limited executor.
        """
        self.executor = executor
        self.rate_limiter = rate_limiter
    
    async def execute(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None
    ) -> List[ToolResult]:
        """
        Execute tool calls with rate limiting.
        """
        # Apply rate limiting to each call
        for call in calls:
            await self.rate_limiter.wait(call.tool)
        # Delegate to inner executor
        return await self.executor.execute(calls, timeout=timeout)


def rate_limited(limit: int, period: float = 60.0):
    """
    Decorator to specify rate limits for a tool class.
    """
    def decorator(cls):
        cls._rate_limit = limit
        cls._rate_period = period
        return cls
    return decorator
