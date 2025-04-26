# chuk_tool_processor/execution/tool_executor.py
from typing import List, Optional

# Lazy import of in-process strategy to allow monkeypatching
import chuk_tool_processor.execution.strategies.inprocess_strategy as inprocess_mod
from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.registry.interface import ToolRegistryInterface

class ToolExecutor:
    """
    Wraps an ExecutionStrategy (in‐process or subprocess) and provides
    a default_timeout shortcut for convenience.
    """
    def __init__(
        self,
        registry: ToolRegistryInterface,
        default_timeout: float = 1.0,
        strategy: Optional[ExecutionStrategy] = None,
        # allow passing through to SubprocessStrategy if needed:
        strategy_kwargs: dict = {}
    ):
        # If user supplied a strategy, use it; otherwise default to in-process
        if strategy is not None:
            self.strategy = strategy
        else:
            # Use module-level InProcessStrategy, so monkeypatching works
            # Pass positional args to match patched FakeInProcess signature
            self.strategy = inprocess_mod.InProcessStrategy(
                registry,
                default_timeout,
                **strategy_kwargs
            )
        self.registry = registry

    async def execute(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None
    ) -> List[ToolResult]:
        """
        Execute the list of calls with the underlying strategy.
        `timeout` here overrides the strategy's default_timeout.
        """
        return await self.strategy.run(calls, timeout=timeout)
