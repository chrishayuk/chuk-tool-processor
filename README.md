# CHUK Tool Processor - Architectural Analysis

## Overview
The CHUK Tool Processor is a sophisticated async-native framework for registering, discovering, and executing tools referenced in LLM responses. Built from the ground up for production use with comprehensive error handling, monitoring, and scalability features. It features a modular architecture with multiple transport mechanisms, execution strategies, and comprehensive tooling for production use.

## Quick Start Example
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
            
        return {"operation": operation, "operands": [a, b], "result": result}

async def main():
    # 2. Initialize the system
    await initialize()
    
    # 3. Process LLM output containing tool calls
    processor = ToolProcessor()
    results = await processor.process('''
        <tool name="calculator" args='{"operation": "multiply", "a": 15, "b": 23}'/>
    ''')
    
    # 4. Handle results
    for result in results:
        if result.error:
            print(f"❌ Tool '{result.tool}' failed: {result.error}")
        else:
            print(f"✅ Tool '{result.tool}' result: {result.result}")

asyncio.run(main())
```

## Key Features & Benefits

- **🔄 Async-Native**: Built for `async/await` from the ground up for optimal performance
- **🛡️ Production Ready**: Comprehensive error handling, timeouts, retries, and monitoring
- **📦 Multiple Execution Strategies**: In-process for speed, subprocess for isolation
- **🚀 High Performance**: Built-in caching, rate limiting, and concurrency control
- **📊 Observability**: Structured logging, metrics collection, and request tracing
- **🔗 MCP Integration**: Full Model Context Protocol support (STDIO, SSE, HTTP Streamable)
- **📡 Streaming Support**: Real-time incremental results for long-running operations
- **🔧 Extensible Architecture**: Plugin system for custom parsers and execution strategies
- **🎯 Multiple Input Formats**: XML tags, OpenAI tool_calls, JSON, function_call formats
- **⚡ Zero-Config Start**: Works out of the box with sensible defaults

## Core Architecture

### Installation & Setup

```bash
# From source (recommended for development)
git clone https://github.com/chrishayuk/chuk-tool-processor.git
cd chuk-tool-processor
pip install -e .

# Or install from PyPI (when available)
pip install chuk-tool-processor
```

### Environment Configuration
```bash
# Optional: Registry provider (default: memory)
export CHUK_TOOL_REGISTRY_PROVIDER=memory

# Optional: Default timeout (default: 30.0)
export CHUK_DEFAULT_TIMEOUT=30.0

# Optional: Enable structured JSON logging
export CHUK_STRUCTURED_LOGGING=true

# MCP Integration (if using external MCP servers)
export MCP_BEARER_TOKEN=your_bearer_token_here
```
### 1. Registry System
- **Interface-driven**: `ToolRegistryInterface` protocol defines the contract
- **Async-native**: All registry operations are async
- **Namespace support**: Tools are organized into namespaces (default: "default")
- **Metadata tracking**: Rich metadata with `ToolMetadata` model
- **Provider pattern**: `ToolRegistryProvider` for singleton management

```python
# Example registry usage
registry = await ToolRegistryProvider.get_registry()
await registry.register_tool(MyTool(), name="my_tool", namespace="custom")
tool = await registry.get_tool("my_tool", "custom")
```

### 2. Tool Development Patterns

#### Simple Function-Based Tools
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

#### ValidatedTool (Declarative with Pydantic)
```python
@register_tool(name="weather", namespace="api")
class WeatherTool(ValidatedTool):
    class Arguments(BaseModel):
        location: str = Field(..., description="City name or coordinates")
        units: str = Field("metric", description="Temperature units")
    
    class Result(BaseModel):
        location: str
        temperature: float
        conditions: str
    
    async def _execute(self, location: str, units: str) -> Result:
        # Implementation here
        return self.Result(location=location, temperature=22.5, conditions="Sunny")
```

#### StreamingTool (Real-time Results)
```python
@register_tool(name="file_processor")
class FileProcessorTool(StreamingTool):
    class Arguments(BaseModel):
        file_path: str
        operation: str = "count_lines"
    
    class Result(BaseModel):
        line_number: int
        content: str
    
    async def _stream_execute(self, file_path: str, operation: str):
        """Stream results as each line is processed."""
        for i in range(1, 100):
            await asyncio.sleep(0.01)  # Simulate processing
            yield self.Result(line_number=i, content=f"Processed line {i}")
```

### 3. Processing LLM Responses

The processor automatically detects and parses multiple input formats:

```python
processor = ToolProcessor()

# 1. XML Tool Tags (most common)
xml_response = """
<tool name="search" args='{"query": "Python programming", "limit": 5}'/>
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
    {"tool": "search", "arguments": {"query": "Python programming", "limit": 5}},
    {"tool": "get_current_time", "arguments": {"timezone": "UTC"}}
]

# Process any format
results1 = await processor.process(xml_response)
results2 = await processor.process(openai_response) 
results3 = await processor.process(tool_calls)
```

### 4. Execution Strategies

#### InProcessStrategy (Default - Fast & Efficient)
- **Concurrent execution**: Uses asyncio for parallelism within the same process
- **Semaphore-based limiting**: Optional max_concurrency control
- **True streaming support**: Direct access to `stream_execute` methods
- **Enhanced tool resolution**: Namespace fallback logic with fuzzy matching
- **Proper timeout handling**: Always applies concrete timeouts

#### SubprocessStrategy (Isolation & Safety)
- **Process isolation**: Each tool runs in separate OS process for safety
- **Serialization support**: Handles complex objects and Pydantic models properly
- **Worker pool management**: Concurrent futures with automatic cleanup
- **Enhanced error handling**: Broken pool recovery and restart
- **Timeout coordination**: Safety timeouts prevent worker hangs

```python
# Configure execution strategy
from chuk_tool_processor.execution.strategies.subprocess_strategy import SubprocessStrategy

processor = ToolProcessor(
    strategy=SubprocessStrategy(
        registry=await get_default_registry(),
        max_workers=4,
        default_timeout=30.0
    )
)
```

### 5. Production Features & Wrappers

#### Caching for Performance
```python
from chuk_tool_processor.execution.wrappers.caching import cacheable

@cacheable(ttl=600)  # Cache for 10 minutes
@register_tool(name="expensive_api")
class ExpensiveApiTool(ValidatedTool):
    # Tool implementation
    pass

# Or configure at processor level
processor = ToolProcessor(
    enable_caching=True,
    cache_ttl=300  # 5 minutes default
)
```

#### Rate Limiting
```python
from chuk_tool_processor.execution.wrappers.rate_limiting import rate_limited

@rate_limited(limit=20, period=60.0)  # 20 calls per minute
@register_tool(name="api_tool")
class ApiTool(ValidatedTool):
    # Tool implementation  
    pass

# Or processor-level configuration
processor = ToolProcessor(
    enable_rate_limiting=True,
    global_rate_limit=100,  # 100 requests per minute globally
    tool_rate_limits={
        "expensive_api": (10, 60),    # 10 per minute for specific tool
    }
)
```

#### Automatic Retries
```python
from chuk_tool_processor.execution.wrappers.retry import retryable

@retryable(max_retries=3, base_delay=1.0)
@register_tool(name="unreliable_api")
class UnreliableApiTool(ValidatedTool):
    # Tool implementation
    pass

# Processor-level retry configuration
processor = ToolProcessor(
    enable_retries=True,
    max_retries=3
)
```

### 6. MCP (Model Context Protocol) Integration

Connect to external tool servers using multiple transport protocols:

#### Quick MCP Setup with SSE (Server-Sent Events)
```python
from chuk_tool_processor.mcp import setup_mcp_sse

# Configure external MCP servers
servers = [
    {
        "name": "weather-service",
        "url": "https://weather-mcp.example.com",
        "api_key": "your_weather_api_key"
    },
    {
        "name": "database-service", 
        "url": "https://db-mcp.example.com",
        "api_key": "your_db_api_key"
    }
]

# Initialize with full production configuration
processor, stream_manager = await setup_mcp_sse(
    servers=servers,
    namespace="mcp",           # Tools available as mcp.tool_name
    default_timeout=30.0,
    enable_caching=True,
    enable_retries=True
)

# Use external tools through MCP
results = await processor.process('''
<tool name="mcp.weather" args='{"location": "London"}'/>
<tool name="mcp.database_query" args='{"sql": "SELECT COUNT(*) FROM users"}'/>
''')
```

#### STDIO Transport (Process-based)
```python
from chuk_tool_processor.mcp import setup_mcp_stdio

# Create MCP config for local processes
mcp_config = {
    "weather": {
        "command": "python", 
        "args": ["-m", "weather_mcp_server"],
        "env": {"API_KEY": "your_weather_key"}
    }
}

processor, stream_manager = await setup_mcp_stdio(
    config_file="mcp_config.json",
    servers=["weather"],
    namespace="tools"
)
```

#### Supported Transports
- **STDIO**: Process-based communication for local MCP servers
- **SSE**: Server-Sent Events for cloud-based MCP services  
- **HTTP Streamable**: Modern HTTP-based transport (spec 2025-03-26)

### 7. Monitoring & Observability

#### Structured Logging
```python
from chuk_tool_processor.logging import setup_logging, get_logger, log_context_span

# Setup structured logging
await setup_logging(
    level=logging.INFO,
    structured=True,  # JSON output for production
    log_file="tool_processor.log"
)

# Use contextual logging
logger = get_logger("my_app")

async def process_user_request(user_id: str, request: str):
    async with log_context_span("user_request", {"user_id": user_id}):
        logger.info("Processing user request", extra={
            "request_length": len(request),
            "user_id": user_id
        })
        
        results = await processor.process(request)
        
        logger.info("Request processed successfully", extra={
            "num_tools": len(results),
            "success_rate": sum(1 for r in results if not r.error) / len(results)
        })
```

#### Automatic Metrics Collection
```python
# Metrics are automatically collected for:
# - Tool execution success/failure rates
# - Execution durations and performance
# - Cache hit/miss rates and efficiency  
# - Parser performance and accuracy
# - Registry operations and health

# Access programmatic metrics
from chuk_tool_processor.logging import metrics

# Custom metrics
await metrics.log_tool_execution(
    tool="custom_metric",
    success=True,
    duration=1.5,
    cached=False,
    attempts=1
)
```

### 8. Error Handling & Best Practices

#### Robust Error Handling
```python
async def robust_tool_processing(llm_response: str):
    """Example of production-ready error handling."""
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
                logger.error(f"Tool {result.tool} failed: {result.error}", extra={
                    "tool": result.tool,
                    "duration": result.duration,
                    "attempts": getattr(result, "attempts", 1)
                })
            else:
                successful_results.append(result)
                logger.info(f"Tool {result.tool} succeeded", extra={
                    "tool": result.tool,
                    "duration": result.duration,
                    "cached": getattr(result, "cached", False)
                })
        
        return {
            "successful": successful_results,
            "failed": failed_results,
            "success_rate": len(successful_results) / len(results) if results else 0
        }
        
    except Exception as e:
        logger.exception("Failed to process LLM response")
        raise
```

#### Testing Your Tools
```python
import pytest
from chuk_tool_processor import ToolProcessor, initialize

@pytest.mark.asyncio
async def test_calculator_tool():
    await initialize()
    processor = ToolProcessor()
    
    results = await processor.process(
        '<tool name="calculator" args=\'{"operation": "add", "a": 5, "b": 3}\'/>'
    )
    
    assert len(results) == 1
    result = results[0]
    assert result.error is None
    assert result.result["result"] == 8
```

## Advanced Configuration

### Production-Ready Setup
```python
from chuk_tool_processor import ToolProcessor
from chuk_tool_processor.execution.strategies.subprocess_strategy import SubprocessStrategy

async def create_production_processor():
    """Configure processor for high-throughput production use."""
    
    processor = ToolProcessor(
        # Execution settings
        default_timeout=30.0,
        max_concurrency=20,        # Allow 20 concurrent executions
        
        # Use subprocess strategy for isolation
        strategy=SubprocessStrategy(
            registry=await get_default_registry(),
            max_workers=8,           # 8 worker processes
            default_timeout=30.0
        ),
        
        # Performance optimizations
        enable_caching=True,
        cache_ttl=900,             # 15-minute cache
        
        # Rate limiting to prevent abuse
        enable_rate_limiting=True,
        global_rate_limit=500,     # 500 requests per minute globally
        tool_rate_limits={
            "expensive_api": (10, 60),    # 10 per minute
            "file_processor": (5, 60),    # 5 per minute
        },
        
        # Reliability features
        enable_retries=True,
        max_retries=3,
        
        # Input parsing
        parser_plugins=["xml_tool", "openai_tool", "json_tool"]
    )
    
    await processor.initialize()
    return processor
```

### Performance Optimization
```python
# Concurrent batch processing
async def process_batch(requests: list[str]):
    """Process multiple LLM responses concurrently."""
    processor = await create_production_processor()
    
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

# Memory management for long-running applications
async def maintenance_task():
    """Periodic maintenance for production deployments."""
    while True:
        await asyncio.sleep(3600)  # Every hour
        
        # Clear old cache entries
        if hasattr(processor.executor, 'cache'):
            await processor.executor.cache.clear()
            logger.info("Cache cleared for memory management")
```

## Key Design Patterns

1. **Async-First Design**: All core operations use async/await with proper timeout handling, graceful cancellation support, and comprehensive resource cleanup via context managers.

2. **Strategy Pattern**: Pluggable execution strategies (InProcess vs Subprocess), composable wrapper chains, and interface-driven design for maximum flexibility.

3. **Registry Pattern**: Centralized tool management with namespace isolation, rich metadata tracking, and lazy initialization for optimal resource usage.

4. **Plugin Architecture**: Discoverable parsers for different input formats, transport abstractions for MCP integration, and extensible validation systems.

5. **Producer-Consumer**: Queue-based streaming architecture for real-time results, with proper backpressure handling and timeout coordination.

6. **Decorator Pattern**: Composable execution wrappers (caching, retries, rate limiting) that can be stacked and configured independently.

## Configuration Reference

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `CHUK_TOOL_REGISTRY_PROVIDER` | `memory` | Registry backend (memory, redis, etc.) |
| `CHUK_DEFAULT_TIMEOUT` | `30.0` | Default tool execution timeout (seconds) |
| `CHUK_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `CHUK_STRUCTURED_LOGGING` | `true` | Enable JSON structured logging |
| `CHUK_MAX_CONCURRENCY` | `10` | Default max concurrent executions |
| `MCP_BEARER_TOKEN` | - | Bearer token for MCP SSE authentication |

### ToolProcessor Options
```python
processor = ToolProcessor(
    # Core execution
    default_timeout=30.0,              # Default timeout per tool
    max_concurrency=10,                # Max concurrent executions
    
    # Strategy selection
    strategy=InProcessStrategy(...),   # Fast, shared memory
    # strategy=SubprocessStrategy(...), # Isolated, safer for untrusted code
    
    # Performance features
    enable_caching=True,               # Result caching
    cache_ttl=300,                     # Cache TTL in seconds
    enable_rate_limiting=False,        # Rate limiting
    enable_retries=True,               # Automatic retries
    max_retries=3,                     # Max retry attempts
    
    # Input processing
    parser_plugins=["xml_tool", "openai_tool", "json_tool"]
)
```

## Why Choose CHUK Tool Processor?

### Built for Production
- **Battle-tested**: Comprehensive error handling, timeout management, and resource cleanup
- **Scalable**: Support for high-throughput concurrent execution with configurable limits
- **Observable**: Built-in structured logging, metrics collection, and request tracing
- **Reliable**: Automatic retries, circuit breakers, and graceful degradation

### Developer Experience
- **Zero-config start**: Works out of the box with sensible defaults
- **Type-safe**: Full Pydantic integration for argument and result validation  
- **Multiple paradigms**: Support for functions, classes, and streaming tools
- **Flexible inputs**: Handles XML tags, OpenAI format, JSON, and direct objects

### Enterprise Ready
- **Process isolation**: Subprocess strategy for running untrusted code safely
- **Rate limiting**: Global and per-tool rate limiting with sliding window algorithm
- **Caching layer**: Intelligent caching with TTL and invalidation strategies  
- **MCP integration**: Connect to external tool servers using industry standards

### Performance Optimized
- **Async-native**: Built from ground up for `async/await` with proper concurrency
- **Streaming support**: Real-time incremental results for long-running operations
- **Resource efficient**: Lazy initialization, connection pooling, and memory management
- **Configurable strategies**: Choose between speed (in-process) and safety (subprocess)

## Getting Started

### 1. Installation
```bash
# From source (recommended for development)
git clone https://github.com/chrishayuk/chuk-tool-processor.git
cd chuk-tool-processor
pip install -e .

# Or install from PyPI (when available)
pip install chuk-tool-processor
```

### 2. Quick Example
```python
import asyncio
from chuk_tool_processor import ToolProcessor, register_tool, initialize

@register_tool(name="hello")
class HelloTool:
    async def execute(self, name: str) -> str:
        return f"Hello, {name}!"

async def main():
    await initialize()
    processor = ToolProcessor()
    
    results = await processor.process(
        '<tool name="hello" args=\'{"name": "World"}\'/>'
    )
    
    print(results[0].result)  # Output: Hello, World!

asyncio.run(main())
```

### 3. Next Steps
- Review the [Architecture Guide](docs/architecture.md) for deeper understanding
- Check out [Tool Development Guide](docs/tools.md) for advanced patterns
- Explore [MCP Integration](docs/mcp.md) for external tool servers
- See [Production Deployment](docs/deployment.md) for scaling considerations

## Contributing & Support

- **GitHub**: [chrishayuk/chuk-tool-processor](https://github.com/chrishayuk/chuk-tool-processor)
- **Issues**: [Report bugs and request features](https://github.com/chrishayuk/chuk-tool-processor/issues)
- **Discussions**: [Community discussions](https://github.com/chrishayuk/chuk-tool-processor/discussions)
- **License**: MIT - see [LICENSE](LICENSE) file for details

Built with ❤️ by the CHUK AI team for the LLM tool integration community.