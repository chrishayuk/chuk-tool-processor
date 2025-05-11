# chuk_tool_processor/execution/wrappers/retry.py
"""
Async-native retry wrapper for tool execution.

This module provides a retry mechanism for tool calls that can automatically
retry failed executions based on configurable criteria and backoff strategies.
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type, Union

from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.logging import get_logger

logger = get_logger("chuk_tool_processor.execution.wrappers.retry")


class RetryConfig:
    """
    Configuration for retry behavior.
    
    Attributes:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        jitter: Whether to add random jitter to delays
        retry_on_exceptions: List of exception types to retry on
        retry_on_error_substrings: List of error message substrings to retry on
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
        """
        Determine if a retry should be attempted.
        
        Args:
            attempt: Current attempt number (0-based)
            error: Exception that caused the failure, if any
            error_str: Error message string, if any
            
        Returns:
            True if a retry should be attempted, False otherwise
        """
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
        """
        Calculate the delay for the current attempt with exponential backoff.
        
        Args:
            attempt: Current attempt number (0-based)
            
        Returns:
            Delay in seconds
        """
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        if self.jitter:
            delay *= (0.5 + random.random())
        return delay


class RetryableToolExecutor:
    """
    Wrapper for a tool executor that applies retry logic.
    
    This executor wraps another executor and automatically retries failed
    tool calls based on configured retry policies.
    """
    def __init__(
        self,
        executor: Any,
        default_config: Optional[RetryConfig] = None,
        tool_configs: Optional[Dict[str, RetryConfig]] = None
    ):
        """
        Initialize the retryable executor.
        
        Args:
            executor: The underlying executor to wrap
            default_config: Default retry configuration for all tools
            tool_configs: Tool-specific retry configurations
        """
        self.executor = executor
        self.default_config = default_config or RetryConfig()
        self.tool_configs = tool_configs or {}
    
    def _get_config(self, tool: str) -> RetryConfig:
        """Get the retry configuration for a specific tool."""
        return self.tool_configs.get(tool, self.default_config)
    
    async def execute(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
        use_cache: bool = True
    ) -> List[ToolResult]:
        """
        Execute tool calls with retry logic.
        
        Args:
            calls: List of tool calls to execute
            timeout: Optional timeout for each execution
            use_cache: Whether to use cached results (passed to underlying executor)
            
        Returns:
            List of tool results
        """
        # Handle empty calls list
        if not calls:
            return []
            
        # Execute each call with retries
        results: List[ToolResult] = []
        for call in calls:
            config = self._get_config(call.tool)
            result = await self._execute_with_retry(call, config, timeout, use_cache)
            results.append(result)
        return results
    
    async def _execute_with_retry(
        self,
        call: ToolCall,
        config: RetryConfig,
        timeout: Optional[float],
        use_cache: bool
    ) -> ToolResult:
        """
        Execute a single tool call with retries.
        
        Args:
            call: Tool call to execute
            config: Retry configuration to use
            timeout: Optional timeout for execution
            use_cache: Whether to use cached results
            
        Returns:
            Tool result after retries
        """
        attempt = 0
        last_error: Optional[str] = None
        pid = 0
        machine = "unknown"
        
        while True:
            start_time = datetime.now(timezone.utc)
            
            try:
                # Pass the use_cache parameter if the executor supports it
                executor_kwargs = {"timeout": timeout}
                if hasattr(self.executor, "use_cache"):
                    executor_kwargs["use_cache"] = use_cache
                
                # Execute call
                tool_results = await self.executor.execute([call], **executor_kwargs)
                result = tool_results[0]
                pid = result.pid
                machine = result.machine
                
                # Check for error in result
                if result.error:
                    last_error = result.error
                    if config.should_retry(attempt, error_str=result.error):
                        logger.debug(
                            f"Retrying tool {call.tool} after error: {result.error} (attempt {attempt + 1}/{config.max_retries})"
                        )
                        await asyncio.sleep(config.get_delay(attempt))
                        attempt += 1
                        continue
                        
                    # No retry: if any retries happened, wrap final error
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
                        # Attach attempts
                        final.attempts = attempt + 1  # Include the original attempt
                        return final
                        
                    # No retries occurred, return the original failure
                    result.attempts = 1
                    return result
                
                # Success: attach attempts and return
                result.attempts = attempt + 1  # Include the original attempt
                return result
                
            except Exception as e:
                err_str = str(e)
                last_error = err_str
                
                if config.should_retry(attempt, error=e):
                    logger.info(
                        f"Retrying tool {call.tool} after exception: {err_str} (attempt {attempt + 1}/{config.max_retries})"
                    )
                    await asyncio.sleep(config.get_delay(attempt))
                    attempt += 1
                    continue
                    
                # No more retries: return error result
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
                final_exc.attempts = attempt + 1  # Include the original attempt
                return final_exc


def retryable(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retry_on_exceptions: Optional[List[Type[Exception]]] = None,
    retry_on_error_substrings: Optional[List[str]] = None
):
    """
    Decorator for tool classes to configure retry behavior.
    
    Example:
        @retryable(max_retries=5, base_delay=2.0)
        class MyTool:
            async def execute(self, x: int, y: int) -> int:
                return x + y
                
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        jitter: Whether to add random jitter to delays
        retry_on_exceptions: List of exception types to retry on
        retry_on_error_substrings: List of error message substrings to retry on
        
    Returns:
        Decorated class with retry configuration
    """
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