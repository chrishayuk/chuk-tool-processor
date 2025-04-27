# chuk_tool_processor/core/processor.py
import asyncio
import time
from typing import Any, Dict, List, Optional, Type, Union

# imports
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.registry import ToolRegistryInterface, ToolRegistryProvider
from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.execution.wrappers.caching import CacheInterface, InMemoryCache, CachingToolExecutor
from chuk_tool_processor.execution.wrappers.rate_limiting import RateLimiter, RateLimitedToolExecutor
from chuk_tool_processor.execution.wrappers.retry import RetryConfig, RetryableToolExecutor
from chuk_tool_processor.plugins.discovery import plugin_registry, discover_default_plugins
from chuk_tool_processor.logging import get_logger, log_context_span, request_logging, log_tool_call, metrics


class ToolProcessor:
    """
    Main class for processing tool calls from LLM responses.
    Combines parsing, execution, and result handling.
    """
    def __init__(
        self,
        registry: Optional[ToolRegistryInterface] = None,
        default_timeout: float = 10.0,
        max_concurrency: Optional[int] = None,
        enable_caching: bool = True,
        cache_ttl: int = 300,
        enable_rate_limiting: bool = False,
        global_rate_limit: Optional[int] = None,
        tool_rate_limits: Optional[Dict[str, tuple]] = None,
        enable_retries: bool = True,
        max_retries: int = 3,
        parser_plugins: Optional[List[str]] = None
    ):
        """
        Initialize the tool processor.
        
        Args:
            registry: Tool registry to use. If None, uses the global registry.
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
        
        # Use provided registry or global registry
        self.registry = registry or ToolRegistryProvider.get_registry()
        
        # Create base executor with in-process strategy
        self.strategy = InProcessStrategy(
            registry=self.registry,
            default_timeout=default_timeout,
            max_concurrency=max_concurrency
        )
        
        self.executor = ToolExecutor(
            registry=self.registry,
            default_timeout=default_timeout,
            strategy=self.strategy
        )
        
        # Apply optional wrappers
        if enable_retries:
            self.logger.debug("Enabling retry logic")
            self.executor = RetryableToolExecutor(
                executor=self.executor,
                default_config=RetryConfig(max_retries=max_retries)
            )
        
        if enable_rate_limiting:
            self.logger.debug("Enabling rate limiting")
            rate_limiter = RateLimiter(
                global_limit=global_rate_limit,
                tool_limits=tool_rate_limits
            )
            self.executor = RateLimitedToolExecutor(
                executor=self.executor,
                rate_limiter=rate_limiter
            )
        
        if enable_caching:
            self.logger.debug("Enabling result caching")
            cache = InMemoryCache(default_ttl=cache_ttl)
            self.executor = CachingToolExecutor(
                executor=self.executor,
                cache=cache,
                default_ttl=cache_ttl
            )
        
        # Discover plugins if not already done
        if not plugin_registry.list_plugins().get("parser", []):
            discover_default_plugins()
        
        # Get parser plugins
        if parser_plugins:
            self.parsers = [
                plugin_registry.get_plugin("parser", name)
                for name in parser_plugins
                if plugin_registry.get_plugin("parser", name)
            ]
        else:
            parser_names = plugin_registry.list_plugins().get("parser", [])
            self.parsers = [
                plugin_registry.get_plugin("parser", name)
                for name in parser_names
            ]
        
        self.logger.debug(f"Initialized with {len(self.parsers)} parser plugins")
    
    async def process_text(
        self,
        text: str,
        timeout: Optional[float] = None,
        use_cache: bool = True,
        request_id: Optional[str] = None
    ) -> List[ToolResult]:
        """
        Process text to extract and execute tool calls.
        
        Args:
            text: Text to process.
            timeout: Optional timeout for execution.
            use_cache: Whether to use cached results.
            request_id: Optional request ID for logging.
            
        Returns:
            List of tool results.
        """
        # Create request context
        with request_logging(request_id) as req_id:
            self.logger.debug(f"Processing text ({len(text)} chars)")
            
            # Extract tool calls
            calls = await self._extract_tool_calls(text)
            
            if not calls:
                self.logger.debug("No tool calls found")
                return []
            
            self.logger.debug(f"Found {len(calls)} tool calls")
            
            # Execute tool calls
            with log_context_span("tool_execution", {"num_calls": len(calls)}):
                # Check if any tools are unknown
                tool_names = set(call.tool for call in calls)
                unknown_tools = [
                    name for name in tool_names
                    if not self.registry.get_tool(name)
                ]
                
                if unknown_tools:
                    self.logger.warning(f"Unknown tools: {unknown_tools}")
                
                # Execute tools
                results = await self.executor.execute(calls, timeout=timeout)
                
                # Log metrics for each tool call
                for call, result in zip(calls, results):
                    log_tool_call(call, result)
                    
                    # Record metrics
                    duration = (result.end_time - result.start_time).total_seconds()
                    metrics.log_tool_execution(
                        tool=call.tool,
                        success=result.error is None,
                        duration=duration,
                        error=result.error,
                        cached=getattr(result, "cached", False),
                        attempts=getattr(result, "attempts", 1)
                    )
                
                return results
    
    async def _extract_tool_calls(self, text: str) -> List[ToolCall]:
        """
        Extract tool calls from text using all available parsers.
        
        Args:
            text: Text to parse.
            
        Returns:
            List of tool calls.
        """
        all_calls = []
        
        # Try each parser
        with log_context_span("parsing", {"text_length": len(text)}):
            for parser in self.parsers:
                parser_name = parser.__class__.__name__
                
                with log_context_span(f"parser.{parser_name}", log_duration=True):
                    start_time = time.time()
                    
                    try:
                        # Try to parse
                        calls = parser.try_parse(text)
                        
                        # Log success
                        duration = time.time() - start_time
                        metrics.log_parser_metric(
                            parser=parser_name,
                            success=True,
                            duration=duration,
                            num_calls=len(calls)
                        )
                        
                        # Add calls to result
                        all_calls.extend(calls)
                        
                    except Exception as e:
                        # Log failure
                        duration = time.time() - start_time
                        metrics.log_parser_metric(
                            parser=parser_name,
                            success=False,
                            duration=duration,
                            num_calls=0
                        )
                        self.logger.error(f"Parser {parser_name} failed: {str(e)}")
        
        # Remove duplicates
        unique_calls = {}
        for call in all_calls:
            key = f"{call.tool}:{hash(frozenset(call.arguments.items()))}"
            unique_calls[key] = call
        
        return list(unique_calls.values())


# Create a global processor with default settings
default_processor = ToolProcessor()


async def process_text(
    text: str,
    timeout: Optional[float] = None,
    use_cache: bool = True,
    request_id: Optional[str] = None
) -> List[ToolResult]:
    """
    Process text with the default processor.
    
    Args:
        text: Text to process.
        timeout: Optional timeout for execution.
        use_cache: Whether to use cached results.
        request_id: Optional request ID for logging.
        
    Returns:
        List of tool results.
    """
    return await default_processor.process_text(
        text=text,
        timeout=timeout,
        use_cache=use_cache,
        request_id=request_id
    )