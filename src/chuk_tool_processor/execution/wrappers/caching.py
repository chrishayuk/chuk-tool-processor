# chuk_tool_processor/execution/wrappers/caching.py
import asyncio
import hashlib
import json
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Dict, Optional, Tuple, List, Callable
from pydantic import BaseModel

# imports
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult


class CacheEntry(BaseModel):
    """
    Entry in the tool result cache.
    """
    tool: str
    arguments_hash: str
    result: Any
    created_at: datetime
    expires_at: Optional[datetime] = None


class CacheInterface(ABC):
    """
    Abstract interface for cache implementations.
    """
    @abstractmethod
    async def get(self, tool: str, arguments_hash: str) -> Optional[Any]:
        """
        Get a cached result for a tool with given arguments hash.
        """
        pass
    
    @abstractmethod
    async def set(
        self, 
        tool: str, 
        arguments_hash: str, 
        result: Any, 
        ttl: Optional[int] = None
    ) -> None:
        """
        Set a cached result for a tool with given arguments hash.
        """
        pass
    
    @abstractmethod
    async def invalidate(self, tool: str, arguments_hash: Optional[str] = None) -> None:
        """
        Invalidate cached results for a tool, optionally for specific arguments.
        """
        pass


class InMemoryCache(CacheInterface):
    """
    In-memory implementation of the cache interface.
    """
    def __init__(self, default_ttl: Optional[int] = 300):
        self._cache: Dict[str, Dict[str, CacheEntry]] = {}
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()
    
    async def get(self, tool: str, arguments_hash: str) -> Optional[Any]:
        async with self._lock:
            tool_cache = self._cache.get(tool)
            if not tool_cache:
                return None
            entry = tool_cache.get(arguments_hash)
            if not entry:
                return None
            now = datetime.now()
            if entry.expires_at and entry.expires_at < now:
                del tool_cache[arguments_hash]
                return None
            return entry.result
    
    async def set(
        self, 
        tool: str, 
        arguments_hash: str, 
        result: Any, 
        ttl: Optional[int] = None
    ) -> None:
        async with self._lock:
            if tool not in self._cache:
                self._cache[tool] = {}
            now = datetime.now()
            expires_at = None
            actual_ttl = ttl if ttl is not None else self._default_ttl
            if actual_ttl is not None:
                expires_at = now + timedelta(seconds=actual_ttl)
            entry = CacheEntry(
                tool=tool,
                arguments_hash=arguments_hash,
                result=result,
                created_at=now,
                expires_at=expires_at
            )
            self._cache[tool][arguments_hash] = entry
    
    async def invalidate(self, tool: str, arguments_hash: Optional[str] = None) -> None:
        async with self._lock:
            if tool not in self._cache:
                return
            if arguments_hash is not None:
                self._cache[tool].pop(arguments_hash, None)
            else:
                del self._cache[tool]


class CachingToolExecutor:
    """
    Wrapper for a tool executor that caches results.
    """
    def __init__(
        self,
        executor: Any,
        cache: CacheInterface,
        default_ttl: Optional[int] = None,
        tool_ttls: Optional[Dict[str, int]] = None,
        cacheable_tools: Optional[List[str]] = None
    ):
        self.executor = executor
        self.cache = cache
        self.default_ttl = default_ttl
        self.tool_ttls = tool_ttls or {}
        self.cacheable_tools = cacheable_tools
    
    def _get_arguments_hash(self, arguments: Dict[str, Any]) -> str:
        serialized = json.dumps(arguments, sort_keys=True)
        return hashlib.md5(serialized.encode()).hexdigest()
    
    def _is_cacheable(self, tool: str) -> bool:
        if self.cacheable_tools is None:
            return True
        return tool in self.cacheable_tools
    
    def _get_ttl(self, tool: str) -> Optional[int]:
        return self.tool_ttls.get(tool, self.default_ttl)
    
    async def execute(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
        use_cache: bool = True
    ) -> List[ToolResult]:
        results: List[ToolResult] = []
        uncached_calls: List[Tuple[int, ToolCall]] = []
        
        if use_cache:
            for i, call in enumerate(calls):
                if not self._is_cacheable(call.tool):
                    uncached_calls.append((i, call))
                    continue
                arguments_hash = self._get_arguments_hash(call.arguments)
                cached_result = await self.cache.get(call.tool, arguments_hash)
                if cached_result is not None:
                    now = datetime.now()
                    results.append(ToolResult(
                        tool=call.tool,
                        result=cached_result,
                        error=None,
                        start_time=now,
                        end_time=now,
                        machine="cache",
                        pid=0,
                        cached=True
                    ))
                else:
                    uncached_calls.append((i, call))
        else:
            uncached_calls = [(i, call) for i, call in enumerate(calls)]

        # Early return if all served from cache
        if use_cache and not uncached_calls:
            return results

        if uncached_calls:
            uncached_results = await self.executor.execute(
                [call for _, call in uncached_calls],
                timeout=timeout
            )
            
            if use_cache:
                for idx, result in enumerate(uncached_results):
                    _, call = uncached_calls[idx]
                    if result.error is None and self._is_cacheable(call.tool):
                        arguments_hash = self._get_arguments_hash(call.arguments)
                        ttl = self._get_ttl(call.tool)
                        await self.cache.set(
                            call.tool,
                            arguments_hash,
                            result.result,
                            ttl=ttl
                        )
                        result.cached = False

            final_results: List[ToolResult] = [None] * len(calls)
            uncached_indices = {idx for idx, _ in uncached_calls}
            uncached_iter = iter(uncached_results)
            cache_iter = iter(results)
            for i in range(len(calls)):
                if i in uncached_indices:
                    final_results[i] = next(uncached_iter)
                else:
                    final_results[i] = next(cache_iter)
            return final_results


def cacheable(ttl: Optional[int] = None):
    def decorator(cls):
        cls._cacheable = True
        if ttl is not None:
            cls._cache_ttl = ttl
        return cls
    return decorator


def invalidate_cache(tool: str, arguments: Optional[Dict[str, Any]] = None):
    async def _invalidate(cache: CacheInterface):
        if arguments is not None:
            arguments_hash = hashlib.md5(
                json.dumps(arguments, sort_keys=True).encode()
            ).hexdigest()
            await cache.invalidate(tool, arguments_hash)
        else:
            await cache.invalidate(tool)
    return _invalidate
