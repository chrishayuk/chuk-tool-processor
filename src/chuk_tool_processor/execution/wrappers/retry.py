# chuk_tool_processor/retry.py
import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type

# imports
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult

logger = logging.getLogger(__name__)


class RetryConfig:
    """
    Configuration for retry behavior.
    """
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
        retry_on_exceptions: Optional[List[Type[Exception]]] = None,
        retry_on_error_substrings: Optional[List[str]] = None
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.retry_on_exceptions = retry_on_exceptions or []
        self.retry_on_error_substrings = retry_on_error_substrings or []
    
    def should_retry(self, attempt: int, error: Optional[Exception] = None, error_str: Optional[str] = None) -> bool:
        if attempt >= self.max_retries:
            return False
        if not self.retry_on_exceptions and not self.retry_on_error_substrings:
            return True
        if error is not None and any(isinstance(error, exc) for exc in self.retry_on_exceptions):
            return True
        if error_str and any(substr in error_str for substr in self.retry_on_error_substrings):
            return True
        return False
    
    def get_delay(self, attempt: int) -> float:
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        if self.jitter:
            delay *= (0.5 + random.random())
        return delay


class RetryableToolExecutor:
    """
    Wrapper for a tool executor that applies retry logic.
    """
    def __init__(
        self,
        executor: Any,
        default_config: RetryConfig = None,
        tool_configs: Dict[str, RetryConfig] = None
    ):
        self.executor = executor
        self.default_config = default_config or RetryConfig()
        self.tool_configs = tool_configs or {}
    
    def _get_config(self, tool: str) -> RetryConfig:
        return self.tool_configs.get(tool, self.default_config)
    
    async def execute(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None
    ) -> List[ToolResult]:
        results: List[ToolResult] = []
        for call in calls:
            config = self._get_config(call.tool)
            result = await self._execute_with_retry(call, config, timeout)
            results.append(result)
        return results
    
    async def _execute_with_retry(
        self,
        call: ToolCall,
        config: RetryConfig,
        timeout: Optional[float]
    ) -> ToolResult:
        attempt = 0
        last_error: Optional[str] = None
        pid = 0
        machine = "unknown"
        
        while True:
            start_time = datetime.now(timezone.utc)
            try:
                # execute call
                tool_results = await self.executor.execute([call], timeout=timeout)
                result = tool_results[0]
                pid = result.pid
                machine = result.machine
                
                # error in result
                if result.error:
                    last_error = result.error
                    if config.should_retry(attempt, error_str=result.error):
                        logger.debug(
                            f"Retrying tool {call.tool} after error: {result.error} (attempt {attempt + 1})"
                        )
                        await asyncio.sleep(config.get_delay(attempt))
                        attempt += 1
                        continue
                    # no retry: if any retries happened, wrap final error
                    if attempt > 0:
                        end_time = datetime.now(timezone.utc)
                        final = ToolResult(
                            tool=call.tool,
                            result=None,
                            error=f"Max retries reached ({config.max_retries}): {last_error}",
                            start_time=start_time,
                            end_time=end_time,
                            machine=machine,
                            pid=pid
                        )
                        # attach attempts
                        object.__setattr__(final, 'attempts', attempt)
                        return final
                    # no retries occurred, return the original failure
                    return result
                
                # success: attach attempts and return
                object.__setattr__(result, 'attempts', attempt)
                return result
            except Exception as e:
                err_str = str(e)
                last_error = err_str
                if config.should_retry(attempt, error=e):
                    logger.info(
                        f"Retrying tool {call.tool} after exception: {err_str} (attempt {attempt + 1})"
                    )
                    await asyncio.sleep(config.get_delay(attempt))
                    attempt += 1
                    continue
                # no more retries: return error result
                end_time = datetime.now(timezone.utc)
                final_exc = ToolResult(
                    tool=call.tool,
                    result=None,
                    error=err_str,
                    start_time=start_time,
                    end_time=end_time,
                    machine=machine,
                    pid=pid
                )
                object.__setattr__(final_exc, 'attempts', attempt + 1)
                return final_exc


def retryable(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retry_on_exceptions: Optional[List[Type[Exception]]] = None,
    retry_on_error_substrings: Optional[List[str]] = None
):
    def decorator(cls):
        cls._retry_config = RetryConfig(
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            jitter=jitter,
            retry_on_exceptions=retry_on_exceptions,
            retry_on_error_substrings=retry_on_error_substrings
        )
        return cls
    return decorator
