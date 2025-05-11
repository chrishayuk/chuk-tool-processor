# chuk_tool_processor/core/processor.py
"""
Async-native core processor for tool execution.

This module provides the central ToolProcessor class which handles:
- Tool call parsing from various input formats
- Tool execution using configurable strategies
- Application of execution wrappers (caching, retries, etc.)
"""
from __future__ import annotations

import asyncio
import time
import json
import hashlib
from typing import Any, Dict, List, Optional, Type, Union, Set

from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.registry import ToolRegistryInterface, ToolRegistryProvider
from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.execution.wrappers.caching import CacheInterface, InMemoryCache, CachingToolExecutor
from chuk_tool_processor.execution.wrappers.rate_limiting import RateLimiter, RateLimitedToolExecutor
from chuk_tool_processor.execution.wrappers.retry import RetryConfig, RetryableToolExecutor
from chuk_tool_processor.plugins.discovery import plugin_registry, discover_default_plugins
from chuk_tool_processor.logging import get_logger, log_context_span, request_logging, log_tool_call, metrics


class ToolProcessor:
    """
    Main class for processing tool calls from LLM responses.
    Combines parsing, execution, and result handling with full async support.
    """

    def __init__(
        self,
        registry: Optional[ToolRegistryInterface] = None,
        strategy = None,
        default_timeout: float = 10.0,
        max_concurrency: Optional[int] = None,
        enable_caching: bool = True,
        cache_ttl: int = 300,
        enable_rate_limiting: bool = False,
        global_rate_limit: Optional[int] = None,
        tool_rate_limits: Optional[Dict[str, tuple]] = None,
        enable_retries: bool = True,
        max_retries: int = 3,
        parser_plugins: Optional[List[str]] = None,
    ):
        """
        Initialize the tool processor.

        Args:
            registry: Tool registry to use. If None, uses the global registry.
            strategy: Optional execution strategy (default: InProcessStrategy)
            default_timeout: Default timeout for tool execution in seconds.
            max_concurrency: Maximum number of concurrent tool executions.
            enable_caching: Whether to enable result caching.
            cache_ttl: Default cache TTL in seconds.
            enable_rate_limiting: Whether to enable rate limiting.
            global_rate_limit: Optional global rate limit (requests per minute).
            tool_rate_limits: Dict mapping tool names to (limit, period) tuples.
            enable_retries: Whether to enable automatic retries.
            max_retries: Maximum number of retry attempts.
            parser_plugins: List of parser plugin names to use.
                If None, uses all available parsers.
        """
        self.logger = get_logger("chuk_tool_processor.processor")
        
        # Store initialization parameters for lazy initialization
        self._registry = registry
        self._strategy = strategy
        self.default_timeout = default_timeout
        self.max_concurrency = max_concurrency
        self.enable_caching = enable_caching
        self.cache_ttl = cache_ttl
        self.enable_rate_limiting = enable_rate_limiting
        self.global_rate_limit = global_rate_limit
        self.tool_rate_limits = tool_rate_limits
        self.enable_retries = enable_retries
        self.max_retries = max_retries
        self.parser_plugin_names = parser_plugins
        
        # Placeholder for initialized components
        self.registry = None
        self.strategy = None
        self.executor = None
        self.parsers = []
        
        # Flag for tracking initialization state
        self._initialized = False
        self._init_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """
        Initialize the processor asynchronously.
        
        This method ensures all components are properly initialized before use.
        It is called automatically by other methods if needed.
        """
        # Fast path if already initialized
        if self._initialized:
            return
            
        # Ensure only one initialization happens at a time
        async with self._init_lock:
            # Double-check pattern after acquiring lock
            if self._initialized:
                return
                
            self.logger.debug("Initializing tool processor")
            
            # Get the registry
            if self._registry is not None:
                self.registry = self._registry
            else:
                self.registry = await ToolRegistryProvider.get_registry()
            
            # Create execution strategy if needed
            if self._strategy is not None:
                self.strategy = self._strategy
            else:
                self.strategy = InProcessStrategy(
                    registry=self.registry,
                    default_timeout=self.default_timeout,
                    max_concurrency=self.max_concurrency,
                )
            
            # Set up the executor chain with optional wrappers
            executor = self.strategy
            
            # Apply wrappers in reverse order (innermost first)
            if self.enable_retries:
                self.logger.debug("Enabling retry logic")
                executor = RetryableToolExecutor(
                    executor=executor,
                    default_config=RetryConfig(max_retries=self.max_retries),
                )
                
            if self.enable_rate_limiting:
                self.logger.debug("Enabling rate limiting")
                rate_limiter = RateLimiter(
                    global_limit=self.global_rate_limit,
                    tool_limits=self.tool_rate_limits,
                )
                executor = RateLimitedToolExecutor(
                    executor=executor,
                    limiter=rate_limiter,
                )
                
            if self.enable_caching:
                self.logger.debug("Enabling result caching")
                cache = InMemoryCache(default_ttl=self.cache_ttl)
                executor = CachingToolExecutor(
                    executor=executor,
                    cache=cache,
                    default_ttl=self.cache_ttl,
                )
            
            self.executor = executor
            
            # Initialize parser plugins
            # Discover plugins if not already done
            plugins = plugin_registry.list_plugins().get("parser", [])
            if not plugins:
                discover_default_plugins()
                plugins = plugin_registry.list_plugins().get("parser", [])
                
            # Get parser plugins
            if self.parser_plugin_names:
                self.parsers = [
                    plugin_registry.get_plugin("parser", name)
                    for name in self.parser_plugin_names
                    if plugin_registry.get_plugin("parser", name)
                ]
            else:
                self.parsers = [
                    plugin_registry.get_plugin("parser", name) for name in plugins
                ]
            
            self.logger.debug(f"Initialized with {len(self.parsers)} parser plugins")
            self._initialized = True

    async def process(
        self,
        data: Union[str, Dict[str, Any], List[Dict[str, Any]]],
        timeout: Optional[float] = None,
        use_cache: bool = True,
        request_id: Optional[str] = None,
    ) -> List[ToolResult]:
        """
        Process tool calls from various input formats.
        
        This method handles different input types:
        - String: Parses tool calls from text using registered parsers
        - Dict: Processes an OpenAI-style tool_calls object
        - List[Dict]: Processes a list of individual tool calls
        
        Args:
            data: Input data containing tool calls
            timeout: Optional timeout for execution
            use_cache: Whether to use cached results
            request_id: Optional request ID for logging
            
        Returns:
            List of tool results
        """
        # Ensure initialization
        await self.initialize()
        
        # Create request context
        async with request_logging(request_id) as req_id:
            # Handle different input types
            if isinstance(data, str):
                # Text processing
                self.logger.debug(f"Processing text ({len(data)} chars)")
                calls = await self._extract_tool_calls(data)
            elif isinstance(data, dict):
                # Handle OpenAI format with tool_calls array
                if "tool_calls" in data and isinstance(data["tool_calls"], list):
                    calls = []
                    for tc in data["tool_calls"]:
                        if "function" in tc and isinstance(tc["function"], dict):
                            function = tc["function"]
                            name = function.get("name")
                            args_str = function.get("arguments", "{}")
                            
                            # Parse arguments
                            try:
                                args = json.loads(args_str) if isinstance(args_str, str) else args_str
                            except json.JSONDecodeError:
                                args = {"raw": args_str}
                                
                            if name:
                                calls.append(ToolCall(tool=name, arguments=args, id=tc.get("id")))
                else:
                    # Assume it's a single tool call
                    calls = [ToolCall(**data)]
            elif isinstance(data, list):
                # List of tool calls
                calls = [ToolCall(**tc) for tc in data]
            else:
                self.logger.warning(f"Unsupported input type: {type(data)}")
                return []
                
            if not calls:
                self.logger.debug("No tool calls found")
                return []
                
            self.logger.debug(f"Found {len(calls)} tool calls")
            
            # Execute tool calls
            async with log_context_span("tool_execution", {"num_calls": len(calls)}):
                # Check if any tools are unknown
                unknown_tools = []
                for call in calls:
                    tool = await self.registry.get_tool(call.tool)
                    if not tool:
                        unknown_tools.append(call.tool)
                
                if unknown_tools:
                    self.logger.warning(f"Unknown tools: {unknown_tools}")
                
                # Execute tools
                results = await self.executor.execute(calls, timeout=timeout)
                
                # Log metrics for each tool call
                for call, result in zip(calls, results):
                    await log_tool_call(call, result)
                    
                    # Record metrics
                    duration = (result.end_time - result.start_time).total_seconds()
                    await metrics.log_tool_execution(
                        tool=call.tool,
                        success=result.error is None,
                        duration=duration,
                        error=result.error,
                        cached=getattr(result, "cached", False),
                        attempts=getattr(result, "attempts", 1),
                    )
                
                return results

    async def process_text(
        self,
        text: str,
        timeout: Optional[float] = None,
        use_cache: bool = True,
        request_id: Optional[str] = None,
    ) -> List[ToolResult]:
        """
        Process text to extract and execute tool calls.
        
        Legacy alias for process() with string input.

        Args:
            text: Text to process.
            timeout: Optional timeout for execution.
            use_cache: Whether to use cached results.
            request_id: Optional request ID for logging.

        Returns:
            List of tool results.
        """
        return await self.process(
            data=text,
            timeout=timeout,
            use_cache=use_cache,
            request_id=request_id,
        )
    
    async def execute(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
        use_cache: bool = True,
    ) -> List[ToolResult]:
        """
        Execute a list of ToolCall objects directly.
        
        Args:
            calls: List of tool calls to execute
            timeout: Optional execution timeout
            use_cache: Whether to use cached results
            
        Returns:
            List of tool results
        """
        # Ensure initialization
        await self.initialize()
        
        # Execute with the configured executor
        return await self.executor.execute(
            calls=calls,
            timeout=timeout,
            use_cache=use_cache if hasattr(self.executor, "use_cache") else True
        )

    async def _extract_tool_calls(self, text: str) -> List[ToolCall]:
        """
        Extract tool calls from text using all available parsers.

        Args:
            text: Text to parse.

        Returns:
            List of tool calls.
        """
        all_calls: List[ToolCall] = []

        # Try each parser
        async with log_context_span("parsing", {"text_length": len(text)}):
            parse_tasks = []
            
            # Create parsing tasks
            for parser in self.parsers:
                parse_tasks.append(self._try_parser(parser, text))
                
            # Execute all parsers concurrently
            parser_results = await asyncio.gather(*parse_tasks, return_exceptions=True)
            
            # Collect successful results
            for result in parser_results:
                if isinstance(result, Exception):
                    continue
                if result:
                    all_calls.extend(result)

        # ------------------------------------------------------------------ #
        # Remove duplicates – use a stable digest instead of hashing a
        # frozenset of argument items (which breaks on unhashable types).
        # ------------------------------------------------------------------ #
        def _args_digest(args: Dict[str, Any]) -> str:
            """Return a stable hash for any JSON-serialisable payload."""
            blob = json.dumps(args, sort_keys=True, default=str)
            return hashlib.md5(blob.encode()).hexdigest()

        unique_calls: Dict[str, ToolCall] = {}
        for call in all_calls:
            key = f"{call.tool}:{_args_digest(call.arguments)}"
            unique_calls[key] = call

        return list(unique_calls.values())
    
    async def _try_parser(self, parser, text: str) -> List[ToolCall]:
        """Try a single parser with metrics and logging."""
        parser_name = parser.__class__.__name__
        
        async with log_context_span(f"parser.{parser_name}", log_duration=True):
            start_time = time.time()
            
            try:
                # Try to parse
                calls = await parser.try_parse(text)
                
                # Log success
                duration = time.time() - start_time
                await metrics.log_parser_metric(
                    parser=parser_name,
                    success=True,
                    duration=duration,
                    num_calls=len(calls),
                )
                
                return calls
                
            except Exception as e:
                # Log failure
                duration = time.time() - start_time
                await metrics.log_parser_metric(
                    parser=parser_name,
                    success=False,
                    duration=duration,
                    num_calls=0,
                )
                self.logger.error(f"Parser {parser_name} failed: {str(e)}")
                return []


# Create a global processor instance
_global_processor: Optional[ToolProcessor] = None
_processor_lock = asyncio.Lock()

async def get_default_processor() -> ToolProcessor:
    """Get or initialize the default global processor."""
    global _global_processor
    
    if _global_processor is None:
        async with _processor_lock:
            if _global_processor is None:
                _global_processor = ToolProcessor()
                await _global_processor.initialize()
                
    return _global_processor

async def process(
    data: Union[str, Dict[str, Any], List[Dict[str, Any]]],
    timeout: Optional[float] = None,
    use_cache: bool = True,
    request_id: Optional[str] = None,
) -> List[ToolResult]:
    """
    Process tool calls with the default processor.
    
    Args:
        data: Input data (text, dict, or list of dicts)
        timeout: Optional timeout for execution
        use_cache: Whether to use cached results
        request_id: Optional request ID for logging
        
    Returns:
        List of tool results
    """
    processor = await get_default_processor()
    return await processor.process(
        data=data,
        timeout=timeout,
        use_cache=use_cache,
        request_id=request_id,
    )

async def process_text(
    text: str,
    timeout: Optional[float] = None,
    use_cache: bool = True,
    request_id: Optional[str] = None,
) -> List[ToolResult]:
    """
    Process text with the default processor.
    
    Legacy alias for backward compatibility.

    Args:
        text: Text to process.
        timeout: Optional timeout for execution.
        use_cache: Whether to use cached results.
        request_id: Optional request ID for logging.

    Returns:
        List of tool results.
    """
    processor = await get_default_processor()
    return await processor.process_text(
        text=text,
        timeout=timeout,
        use_cache=use_cache,
        request_id=request_id,
    )