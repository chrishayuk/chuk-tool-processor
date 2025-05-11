# chuk_tool_processor/execution/tool_executor.py
"""
Async-native tool executor for dispatching tool calls to execution strategies.

This module provides the central ToolExecutor class that delegates tool execution
to configured execution strategies.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

# Lazy import so test-suites can monkey-patch `InProcessStrategy`
import chuk_tool_processor.execution.strategies.inprocess_strategy as _inprocess_mod
from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.registry.interface import ToolRegistryInterface
from chuk_tool_processor.logging import get_logger

logger = get_logger("chuk_tool_processor.execution.tool_executor")


class ToolExecutor:
    """
    Async-native executor that selects and uses a strategy for tool execution.
    
    This class provides a unified interface for executing tools using different
    execution strategies. By default, it uses the InProcessStrategy.
    """

    def __init__(
        self,
        registry: Optional[ToolRegistryInterface] = None,
        default_timeout: float = 10.0,
        strategy: Optional[ExecutionStrategy] = None,
        strategy_kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize the tool executor.
        
        Args:
            registry: Tool registry to use for tool lookups
            default_timeout: Default timeout for tool execution
            strategy: Optional execution strategy (default: InProcessStrategy)
            strategy_kwargs: Additional arguments for the strategy constructor
        """
        self.registry = registry
        self.default_timeout = default_timeout
        
        # Create strategy if not provided
        if strategy is None:
            if registry is None:
                raise ValueError("Registry must be provided if strategy is not")
                
            strategy_kwargs = strategy_kwargs or {}
            strategy = _inprocess_mod.InProcessStrategy(
                registry,
                default_timeout=default_timeout,
                **strategy_kwargs,
            )
            
        self.strategy = strategy

    async def execute(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
        use_cache: bool = True,
    ) -> List[ToolResult]:
        """
        Execute tool calls using the configured strategy.
        
        Args:
            calls: List of tool calls to execute
            timeout: Optional timeout for execution (overrides default_timeout)
            use_cache: Whether to use cached results (for caching wrappers)
            
        Returns:
            List of tool results in the same order as calls
        """
        if not calls:
            return []
            
        # Use the provided timeout or fall back to default
        effective_timeout = timeout if timeout is not None else self.default_timeout
        
        logger.debug(f"Executing {len(calls)} tool calls with timeout {effective_timeout}s")
        
        # Delegate to the strategy
        return await self.strategy.run(calls, timeout=effective_timeout)