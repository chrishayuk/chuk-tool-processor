# CHUK Tool Processor

An async-native framework for registering, discovering, and executing tools referenced in LLM responses. Built from the ground up for production use with comprehensive error handling, monitoring, and scalability features.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Async Native](https://img.shields.io/badge/async-native-green.svg)](https://docs.python.org/3/library/asyncio.html)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🚀 Quick Start

### Installation

```bash
# From source (recommended for development)
git clone https://github.com/chrishayuk/chuk-tool-processor.git
cd chuk-tool-processor
pip install -e .

# Or install from PyPI (when available)
pip install chuk-tool-processor
```

### Your First Tool in 60 Seconds

```python
import asyncio
from chuk_tool_processor import ToolProcessor, register_tool, initialize

# 1. Create a tool
@register_tool(name="calculator", description="Perform basic math operations")
class Calculator:
    async def execute(self, operation: str, a: float, b: float) -> dict:
        operations = {
            "add": a + b,
            "subtract": a - b,
            "multiply": a * b,
            "divide": a / b if b != 0 else None
        }
        
        if operation not in operations:
            raise ValueError(f"Unknown operation: {operation}")
        
        result = operations[operation]
        if result is None:
            raise ValueError("Cannot divide by zero")
            
        return {
            "operation": operation,
            "operands": [a, b],
            "result": result
        }

async def main():
    # 2. Initialize the system
    await initialize()
    
    # 3. Create processor
    processor = ToolProcessor()
    
    # 4. Process LLM output containing tool calls
    llm_response = '''
    I'll calculate 15 * 23 for you.
    
    <tool name="calculator" args='{"operation": "multiply", "a": 15, "b": 23}'/>
    
    The result is 345.
    '''
    
    # 5. Execute the tools
    results = await processor.process(llm_response)
    
    # 6. Handle results
    for result in results:
        if result.error:
            print(f"❌ Tool '{result.tool}' failed: {result.error}")
        else:
            print(f"✅ Tool '{result.tool}' result: {result.result}")
            print(f"⏱️  Executed in {result.duration:.3f}s")

if __name__ == "__main__":
    asyncio.run(main())
```

**Output:**
```
✅ Tool 'calculator' result: {'operation': 'multiply', 'operands': [15, 23], 'result': 345}
⏱️  Executed in 0.001s
```

## 🎯 Key Features

- **🔄 Async-Native**: Built for `async/await` from the ground up
- **🛡️ Production Ready**: Comprehensive error handling, timeouts, retries
- **📦 Multiple Execution**: In-process and subprocess strategies
- **🚀 High Performance**: Caching, rate limiting, and concurrency control
- **📊 Monitoring**: Structured logging and metrics collection
- **🔗 MCP Integration**: Full Model Context Protocol support
- **📡 Streaming**: Real-time incremental results
- **🔧 Extensible**: Plugin system for custom parsers and strategies

## 📖 Getting Started Guide

### Environment Setup

Create a `.env` file or set environment variables:

```bash
# Optional: Registry provider (default: memory)
export CHUK_TOOL_REGISTRY_PROVIDER=memory

# Optional: Default timeout for tool execution (default: 30.0)
export CHUK_DEFAULT_TIMEOUT=30.0

# Optional: Logging level (default: INFO)
export CHUK_LOG_LEVEL=INFO

# Optional: Enable structured JSON logging (default: true)
export CHUK_STRUCTURED_LOGGING=true

# MCP Integration (if using MCP servers)
export MCP_BEARER_TOKEN=your_bearer_token_here
export MCP_CONFIG_FILE=/path/to/mcp_config.json
```

### Basic Tool Development

#### 1. Simple Function-Based Tool

```python
from chuk_tool_processor.registry.auto_register import register_fn_tool

async def get_current_time(timezone: str = "UTC") -> str:
    """Get the current time in the specified timezone."""
    from datetime import datetime
    import pytz
    
    tz = pytz.timezone(timezone)
    current_time = datetime.now(tz)
    return current_time.strftime("%Y-%m-%d %H:%M:%S %Z")

# Register the function as a tool
await register_fn_tool(get_current_time, namespace="utilities")
```

#### 2. Class-Based Tool with Validation

```python
from chuk_tool_processor.models.validated_tool import ValidatedTool
from pydantic import BaseModel, Field

@register_tool(name="weather", namespace="api")
class WeatherTool(ValidatedTool):
    """Get weather information for a location."""
    
    class Arguments(BaseModel):
        location: str = Field(..., description="City name or coordinates")
        units: str = Field("metric", description="Temperature units: metric, imperial, kelvin")
        include_forecast: bool = Field(False, description="Include 5-day forecast")
    
    class Result(BaseModel):
        location: str
        temperature: float
        conditions: str
        humidity: int
        forecast: list[dict] = Field(default_factory=list)
    
    async def _execute(self, location: str, units: str, include_forecast: bool) -> Result:
        # Simulate API call
        await asyncio.sleep(0.1)
        
        return self.Result(
            location=location,
            temperature=22.5,
            conditions="Partly cloudy",
            humidity=65,
            forecast=[{"day": "Tomorrow", "temp": 24, "conditions": "Sunny"}] if include_forecast else []
        )
```

#### 3. Streaming Tool

```python
from chuk_tool_processor.models.streaming_tool import StreamingTool
import asyncio

@register_tool(name="file_processor")
class FileProcessorTool(StreamingTool):
    """Process a large file line by line."""
    
    class Arguments(BaseModel):
        file_path: str
        operation: str = "count_lines"
    
    class Result(BaseModel):
        line_number: int
        content: str
        processed_at: str
    
    async def _stream_execute(self, file_path: str, operation: str):
        """Stream results as each line is processed."""
        from datetime import datetime
        
        # Simulate processing a large file
        total_lines = 100
        
        for i in range(1, total_lines + 1):
            await asyncio.sleep(0.01)  # Simulate processing time
            
            yield self.Result(
                line_number=i,
                content=f"Processed line {i}",
                processed_at=datetime.now().isoformat()
            )
```

### Advanced Configuration

#### Production-Ready Processor Setup

```python
from chuk_tool_processor import ToolProcessor
from chuk_tool_processor.execution.strategies.subprocess_strategy import SubprocessStrategy

async def create_production_processor():
    """Create a production-ready processor with all features enabled."""
    
    processor = ToolProcessor(
        # Execution settings
        default_timeout=30.0,
        max_concurrency=10,
        
        # Use subprocess strategy for isolation
        strategy=SubprocessStrategy(
            registry=await get_default_registry(),
            max_workers=4,
            default_timeout=30.0
        ),
        
        # Enable caching for performance
        enable_caching=True,
        cache_ttl=300,  # 5 minutes
        
        # Rate limiting to prevent abuse
        enable_rate_limiting=True,
        global_rate_limit=100,  # 100 requests per minute globally
        tool_rate_limits={
            "expensive_api": (10, 60),    # 10 per minute
            "file_processor": (5, 60),    # 5 per minute
            "weather": (50, 60)           # 50 per minute
        },
        
        # Automatic retries for reliability
        enable_retries=True,
        max_retries=3,
        
        # Specify which parsers to use
        parser_plugins=["xml_tool", "openai_tool", "json_tool", "function_call"]
    )
    
    await processor.initialize()
    return processor
```

#### Custom Tool with All Features

```python
from chuk_tool_processor.execution.wrappers.caching import cacheable
from chuk_tool_processor.execution.wrappers.rate_limiting import rate_limited
from chuk_tool_processor.execution.wrappers.retry import retryable

@register_tool(name="advanced_api", namespace="external")
@cacheable(ttl=600)  # Cache for 10 minutes
@rate_limited(limit=20, period=60.0)  # 20 calls per minute
@retryable(max_retries=3, base_delay=1.0)  # Retry on failures
class AdvancedApiTool(ValidatedTool):
    """Example tool with all production features."""
    
    class Arguments(BaseModel):
        query: str = Field(..., min_length=1, max_length=1000)
        format: str = Field("json", regex="^(json|xml|csv)$")
        timeout: float = Field(10.0, gt=0, le=30)
    
    class Result(BaseModel):
        data: dict
        format: str
        processing_time: float
        cached: bool = False
    
    async def _execute(self, query: str, format: str, timeout: float) -> Result:
        start_time = time.time()
        
        # Simulate expensive API call
        await asyncio.sleep(0.5)
        
        # Simulate potential failure (for retry testing)
        if random.random() < 0.1:  # 10% failure rate
            raise Exception("Temporary API failure")
        
        processing_time = time.time() - start_time
        
        return self.Result(
            data={"query": query, "results": ["result1", "result2", "result3"]},
            format=format,
            processing_time=processing_time
        )
```

### Working with LLM Responses

#### Supported Input Formats

The processor automatically detects and parses multiple formats:

```python
# 1. XML Tool Tags (most common)
xml_response = """
Let me search for information about Python.

<tool name="search" args='{"query": "Python programming", "limit": 5}'/>

I'll also get the current time.

<tool name="get_current_time" args='{"timezone": "UTC"}'/>
"""

# 2. OpenAI Chat Completions Format
openai_response = {
    "tool_calls": [
        {
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "search",
                "arguments": '{"query": "Python programming", "limit": 5}'
            }
        }
    ]
}

# 3. Direct ToolCall objects
tool_calls = [
    {
        "tool": "search",
        "arguments": {"query": "Python programming", "limit": 5}
    },
    {
        "tool": "get_current_time",
        "arguments": {"timezone": "UTC"}
    }
]

# Process any format
processor = ToolProcessor()
results1 = await processor.process(xml_response)
results2 = await processor.process(openai_response)
results3 = await processor.process(tool_calls)
```

#### Error Handling Best Practices

```python
async def robust_tool_processing(llm_response: str):
    """Example of robust error handling."""
    processor = ToolProcessor(
        default_timeout=30.0,
        enable_retries=True,
        max_retries=3
    )
    
    try:
        results = await processor.process(llm_response, timeout=60.0)
        
        successful_results = []
        failed_results = []
        
        for result in results:
            if result.error:
                failed_results.append(result)
                logger.error(
                    f"Tool {result.tool} failed: {result.error}",
                    extra={
                        "tool": result.tool,
                        "duration": result.duration,
                        "attempts": getattr(result, "attempts", 1),
                        "machine": result.machine
                    }
                )
            else:
                successful_results.append(result)
                logger.info(
                    f"Tool {result.tool} succeeded",
                    extra={
                        "tool": result.tool,
                        "duration": result.duration,
                        "cached": getattr(result, "cached", False)
                    }
                )
        
        return {
            "successful": successful_results,
            "failed": failed_results,
            "total": len(results)
        }
        
    except Exception as e:
        logger.exception("Failed to process LLM response")
        raise
```

### MCP (Model Context Protocol) Integration

#### Quick MCP Setup with SSE

```python
from chuk_tool_processor.mcp import setup_mcp_sse
import os

async def setup_mcp_tools():
    """Set up MCP tools from external servers."""
    
    # Configure MCP servers
    servers = [
        {
            "name": "weather-service",
            "url": "https://weather-mcp.example.com",
            "api_key": os.getenv("WEATHER_API_KEY")
        },
        {
            "name": "database-service", 
            "url": "https://db-mcp.example.com",
            "api_key": os.getenv("DB_API_KEY")
        }
    ]
    
    # Initialize MCP with full configuration
    processor, stream_manager = await setup_mcp_sse(
        servers=servers,
        namespace="mcp",           # Tools available as mcp.tool_name
        default_timeout=30.0,
        max_concurrency=5,
        enable_caching=True,
        cache_ttl=300,
        enable_rate_limiting=True,
        global_rate_limit=100,
        enable_retries=True,
        max_retries=3
    )
    
    return processor, stream_manager

# Use MCP tools
processor, manager = await setup_mcp_tools()

# Tools are now available in the processor
results = await processor.process('''
<tool name="mcp.weather" args='{"location": "London"}'/>
<tool name="mcp.database_query" args='{"sql": "SELECT COUNT(*) FROM users"}'/>
''')
```

#### MCP with Stdio Transport

```python
from chuk_tool_processor.mcp import setup_mcp_stdio

# Create MCP config file (mcp_config.json)
mcp_config = {
    "weather": {
        "command": "python",
        "args": ["-m", "weather_mcp_server"],
        "env": {"API_KEY": "your_weather_key"}
    },
    "calculator": {
        "command": "node",
        "args": ["calculator-server.js"]
    }
}

# Setup MCP with stdio
processor, stream_manager = await setup_mcp_stdio(
    config_file="mcp_config.json",
    servers=["weather", "calculator"],
    namespace="tools"
)

# Use the tools
results = await processor.process('<tool name="tools.weather" args=\'{"city": "Paris"}\'/>')
```

### Monitoring and Observability

#### Structured Logging Setup

```python
from chuk_tool_processor.logging import setup_logging, get_logger, log_context_span
import logging

# Setup logging
await setup_logging(
    level=logging.INFO,
    structured=True,  # JSON output
    log_file="tool_processor.log"  # Optional file output
)

# Use structured logging in your application
logger = get_logger("my_app")

async def process_user_request(user_id: str, request: str):
    """Example of using structured logging with context."""
    
    async with log_context_span("user_request", {"user_id": user_id}):
        logger.info("Processing user request", extra={
            "request_length": len(request),
            "user_id": user_id
        })
        
        try:
            results = await processor.process(request)
            
            logger.info("Request processed successfully", extra={
                "num_tools": len(results),
                "user_id": user_id
            })
            
            return results
            
        except Exception as e:
            logger.error("Request processing failed", extra={
                "error": str(e),
                "user_id": user_id
            })
            raise
```

#### Metrics Collection

```python
from chuk_tool_processor.logging import metrics

# Metrics are automatically collected for:
# - Tool execution success/failure rates
# - Execution durations
# - Cache hit/miss rates
# - Parser performance
# - Registry operations

# Access metrics programmatically
async def get_tool_stats():
    """Get statistics about tool usage."""
    
    # Example: Get cache statistics
    if hasattr(processor.executor, 'cache'):
        cache_stats = await processor.executor.cache.get_stats()
        print(f"Cache hit rate: {cache_stats['hit_rate']:.2%}")
        print(f"Total entries: {cache_stats['entry_count']}")
    
    # Custom metrics can be logged
    await metrics.log_tool_execution(
        tool="custom_metric",
        success=True,
        duration=1.5,
        cached=False
    )
```

### Testing Your Tools

#### Unit Testing

```python
import pytest
from chuk_tool_processor import ToolProcessor, register_tool, initialize

@pytest.mark.asyncio
async def test_calculator_tool():
    """Test the calculator tool."""
    
    # Setup
    await initialize()
    processor = ToolProcessor()
    
    # Test successful operation
    results = await processor.process(
        '<tool name="calculator" args=\'{"operation": "add", "a": 5, "b": 3}\'/>'
    )
    
    assert len(results) == 1
    result = results[0]
    assert result.error is None
    assert result.result["result"] == 8
    assert result.result["operation"] == "add"

@pytest.mark.asyncio 
async def test_calculator_error_handling():
    """Test calculator error handling."""
    
    await initialize()
    processor = ToolProcessor()
    
    # Test division by zero
    results = await processor.process(
        '<tool name="calculator" args=\'{"operation": "divide", "a": 5, "b": 0}\'/>'
    )
    
    assert len(results) == 1
    result = results[0]
    assert result.error is not None
    assert "Cannot divide by zero" in result.error
```

#### Integration Testing

```python
@pytest.mark.asyncio
async def test_full_workflow():
    """Test a complete workflow with multiple tools."""
    
    # Register additional test tools
    @register_tool(name="formatter")
    class FormatterTool:
        async def execute(self, text: str, format: str) -> str:
            if format == "upper":
                return text.upper()
            elif format == "lower":
                return text.lower()
            return text
    
    await initialize()
    processor = ToolProcessor(enable_caching=True)
    
    # Test multiple tool calls
    llm_response = """
    <tool name="calculator" args='{"operation": "multiply", "a": 6, "b": 7}'/>
    <tool name="formatter" args='{"text": "Hello World", "format": "upper"}'/>
    """
    
    results = await processor.process(llm_response)
    
    assert len(results) == 2
    
    # Check calculator result
    calc_result = next(r for r in results if r.tool == "calculator")
    assert calc_result.result["result"] == 42
    
    # Check formatter result
    format_result = next(r for r in results if r.tool == "formatter")
    assert format_result.result == "HELLO WORLD"
```

### Performance Optimization

#### Concurrent Execution

```python
# Configure for high-throughput scenarios
processor = ToolProcessor(
    max_concurrency=20,        # Allow 20 concurrent tool executions
    default_timeout=60.0,      # Longer timeout for complex operations
    enable_caching=True,       # Cache frequently used results
    cache_ttl=900,             # 15-minute cache
    enable_rate_limiting=True,
    global_rate_limit=500      # 500 requests per minute
)

# Process multiple requests concurrently
async def process_batch(requests: list[str]):
    """Process multiple LLM responses concurrently."""
    
    tasks = [processor.process(request) for request in requests]
    all_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    successful = []
    failed = []
    
    for i, result in enumerate(all_results):
        if isinstance(result, Exception):
            failed.append({"request_index": i, "error": str(result)})
        else:
            successful.append({"request_index": i, "results": result})
    
    return {"successful": successful, "failed": failed}
```

#### Memory Management

```python
# For long-running applications, periodically clear caches
async def maintenance_task():
    """Periodic maintenance for long-running applications."""
    
    while True:
        await asyncio.sleep(3600)  # Every hour
        
        # Clear old cache entries
        if hasattr(processor.executor, 'cache'):
            # Clear entire cache or implement LRU eviction
            stats_before = await processor.executor.cache.get_stats()
            await processor.executor.cache.clear()
            
            logger.info("Cache cleared", extra={
                "entries_cleared": stats_before.get("entry_count", 0)
            })

# Run maintenance in background
asyncio.create_task(maintenance_task())
```

## 🔧 Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CHUK_TOOL_REGISTRY_PROVIDER` | `memory` | Registry backend (memory, redis, etc.) |
| `CHUK_DEFAULT_TIMEOUT` | `30.0` | Default tool execution timeout (seconds) |
| `CHUK_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `CHUK_STRUCTURED_LOGGING` | `true` | Enable JSON structured logging |
| `CHUK_MAX_CONCURRENCY` | `10` | Default max concurrent executions |
| `MCP_BEARER_TOKEN` | - | Bearer token for MCP SSE authentication |
| `MCP_CONFIG_FILE` | - | Path to MCP configuration file |

### ToolProcessor Configuration

```python
processor = ToolProcessor(
    # Execution
    default_timeout=30.0,              # Default timeout per tool
    max_concurrency=10,                # Max concurrent executions
    
    # Strategy (choose one)
    strategy=InProcessStrategy(...),   # Fast, shared memory
    # strategy=SubprocessStrategy(...), # Isolated, safer
    
    # Caching
    enable_caching=True,               # Enable result caching
    cache_ttl=300,                     # Cache TTL in seconds
    
    # Rate limiting
    enable_rate_limiting=False,        # Enable rate limiting
    global_rate_limit=100,             # Global requests per minute
    tool_rate_limits={                 # Per-tool limits
        "expensive_tool": (10, 60),    # 10 per minute
    },
    
    # Retries
    enable_retries=True,               # Enable automatic retries
    max_retries=3,                     # Max retry attempts
    
    # Parsing
    parser_plugins=[                   # Enabled parsers
        "xml_tool",
        "openai_tool", 
        "json_tool",
        "function_call"
    ]
)
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone and setup development environment
git clone https://github.com/chrishayuk/chuk-tool-processor.git
cd chuk-tool-processor

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode with all extras
pip install -e ".[dev,test,mcp,all]"

# Run tests
pytest

# Run with coverage
pytest --cov=chuk_tool_processor

# Format code
black chuk_tool_processor
isort chuk_tool_processor

# Type checking
mypy chuk_tool_processor
```

### Adding New Features

1. **New Tool Types**: Extend `ValidatedTool` or `StreamingTool`
2. **New Parsers**: Implement `ParserPlugin` interface
3. **New Strategies**: Implement `ExecutionStrategy` interface
4. **New Wrappers**: Create execution wrappers for cross-cutting concerns

## 📚 Documentation

- [API Reference](docs/api.md)
- [Architecture Guide](docs/architecture.md)
- [Plugin Development](docs/plugins.md)
- [MCP Integration Guide](docs/mcp.md)
- [Performance Tuning](docs/performance.md)
- [Deployment Guide](docs/deployment.md)

## 🆘 Support

- [GitHub Issues](https://github.com/chrishayuk/chuk-tool-processor/issues)
- [Discussions](https://github.com/chrishayuk/chuk-tool-processor/discussions)
- [Discord Community](https://discord.gg/chuk-tools)

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Made with ❤️ by the CHUK team**