# CHUK Tool Processor

An async-native framework for registering, discovering, and executing tools referenced in LLM responses.

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/chuk-tool-processor.git
cd chuk-tool-processor

# Install with pip
pip install -e .
```

### Basic Usage

```python
import asyncio
from chuk_tool_processor.registry import register_tool, initialize
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.execution.tool_executor import ToolExecutor

# Register a simple tool
@register_tool(name="calculator", description="Perform basic calculations")
class CalculatorTool:
    async def execute(self, operation: str, x: float, y: float) -> dict:
        if operation == "add":
            result = x + y
        elif operation == "multiply":
            result = x * y
        else:
            raise ValueError(f"Unknown operation: {operation}")
            
        return {
            "operation": operation,
            "x": x,
            "y": y,
            "result": result
        }

# Setup and execute tools
async def main():
    # Initialize registry
    await initialize()
    
    # Get the default registry
    from chuk_tool_processor.registry import get_default_registry
    registry = await get_default_registry()
    
    # Create execution strategy and executor
    strategy = InProcessStrategy(registry)
    executor = ToolExecutor(registry=registry, strategy=strategy)
    
    # Create a tool call
    call = ToolCall(
        tool="calculator",
        arguments={
            "operation": "multiply",
            "x": 5,
            "y": 7
        }
    )
    
    # Execute tool
    results = await executor.execute([call])
    
    # Display result
    result = results[0]
    if not result.error:
        print(f"Result: {result.result}")
    else:
        print(f"Error: {result.error}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Core Features

### Async-Native Architecture

The entire framework is built with native `async/await` support, allowing for:
- Non-blocking execution of tools
- True concurrency with controlled parallelism
- Task-local context tracking across async boundaries

### Tool Registry

Tools are registered in a central registry with optional namespaces:

```python
# Register with default parameters
@register_tool()
class SimpleGreeter:
    async def execute(self, name: str) -> str:
        return f"Hello, {name}!"

# Register with custom name and namespace
@register_tool(name="weather", namespace="api", description="Get weather info")
class WeatherTool:
    async def execute(self, location: str, units: str = "metric") -> dict:
        # Implementation...
        return {"temperature": 23.5, "conditions": "Sunny"}
```

Initialize and access the registry:

```python
# Initialize registry (required at startup)
await initialize()

# Get registry
registry = await get_default_registry()

# Look up a tool
tool = await registry.get_tool("weather", namespace="api")

# List registered tools
tools = await registry.list_tools()

# Get tool metadata
metadata = await registry.get_metadata("weather", namespace="api")
```

### Execution Strategies

Two execution strategies are provided:

#### 1. InProcessStrategy

Executes tools in the same process with optional concurrency control:

```python
from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy

strategy = InProcessStrategy(
    registry,
    default_timeout=10.0,     # Timeout for tool execution
    max_concurrency=5         # Maximum concurrent executions
)
```

#### 2. SubprocessStrategy

Executes tools in separate processes for true isolation:

```python
from chuk_tool_processor.execution.strategies.subprocess_strategy import SubprocessStrategy

strategy = SubprocessStrategy(
    registry,
    max_workers=4,            # Maximum worker processes
    default_timeout=30.0      # Timeout for tool execution
)
```

### Execution Wrappers

Enhance tool execution with optional wrappers:

#### Retry Logic

```python
from chuk_tool_processor.execution.wrappers.retry import RetryConfig, RetryableToolExecutor

# Use as a wrapper
retry_executor = RetryableToolExecutor(
    executor=base_executor,
    default_config=RetryConfig(
        max_retries=3,
        base_delay=0.5,
        jitter=True
    )
)

# Or as a decorator
from chuk_tool_processor.execution.wrappers.retry import retryable

@retryable(max_retries=3, base_delay=0.5)
@register_tool(name="flaky_api")
class FlakyApiTool:
    async def execute(self, query: str) -> dict:
        # Implementation with potential failures
        pass
```

#### Caching

```python
from chuk_tool_processor.execution.wrappers.caching import InMemoryCache, CachingToolExecutor

# Use as a wrapper
cache = InMemoryCache(default_ttl=60)  # 60 second TTL
cache_executor = CachingToolExecutor(
    executor=base_executor,
    cache=cache
)

# Or as a decorator
from chuk_tool_processor.execution.wrappers.caching import cacheable

@cacheable(ttl=300)  # Cache for 5 minutes
@register_tool(name="expensive_operation")
class ExpensiveOperationTool:
    async def execute(self, input_value: int) -> dict:
        # Expensive computation
        pass
```

#### Rate Limiting

```python
from chuk_tool_processor.execution.wrappers.rate_limiting import RateLimiter, RateLimitedToolExecutor

# Use as a wrapper
limiter = RateLimiter(global_limit=100, global_period=60.0)  # 100 requests per minute
rate_limited_executor = RateLimitedToolExecutor(
    executor=base_executor,
    limiter=limiter
)

# Or as a decorator
from chuk_tool_processor.execution.wrappers.rate_limiting import rate_limited

@rate_limited(limit=5, period=60.0)  # 5 requests per minute
@register_tool(name="external_api")
class ExternalApiTool:
    async def execute(self, query: str) -> dict:
        # Call to rate-limited external API
        pass
```

### Streaming Tool Support

Tools can stream results incrementally:

```python
from chuk_tool_processor.models.streaming_tool import StreamingTool
from pydantic import BaseModel, Field
from typing import AsyncIterator

@register_tool(name="counter")
class CounterTool(StreamingTool):
    """Stream incremental counts."""
    
    class Arguments(BaseModel):
        start: int = Field(1, description="Starting value")
        end: int = Field(10, description="Ending value")
        delay: float = Field(0.5, description="Delay between items")
    
    class Result(BaseModel):
        value: int
        timestamp: str
    
    async def _stream_execute(self, start: int, end: int, delay: float) -> AsyncIterator[Result]:
        """Stream each count with a delay."""
        from datetime import datetime
        
        for i in range(start, end + 1):
            await asyncio.sleep(delay)
            yield self.Result(
                value=i,
                timestamp=datetime.now().isoformat()
            )

# Stream results
async for result in executor.stream_execute([tool_call]):
    print(f"Received: {result.result.value}")
```

### Comprehensive Error Handling

Errors are captured in the result objects rather than raising exceptions:

```python
# Execute tool calls
results = await executor.execute([call1, call2, call3])

for result in results:
    if result.error:
        print(f"Tool {result.tool} failed: {result.error}")
        print(f"Duration: {(result.end_time - result.start_time).total_seconds()}s")
    else:
        print(f"Tool {result.tool} succeeded: {result.result}")
```

### Validation

Validate tool arguments and results:

```python
from pydantic import BaseModel
from chuk_tool_processor.models.validated_tool import ValidatedTool

@register_tool(name="validate_data", namespace="utils")
class ValidatedDataTool(ValidatedTool):
    class Arguments(BaseModel):
        username: str
        age: int
        email: str
    
    class Result(BaseModel):
        is_valid: bool
        errors: list[str] = []
    
    async def _execute(self, username: str, age: int, email: str) -> Result:
        errors = []
        
        if len(username) < 3:
            errors.append("Username too short")
        
        if age < 18:
            errors.append("Must be 18 or older")
            
        if "@" not in email:
            errors.append("Invalid email")
            
        return self.Result(
            is_valid=len(errors) == 0,
            errors=errors
        )
```

## Processing LLM Responses

The `ToolProcessor` helps extract and execute tool calls from LLM responses:

```python
from chuk_tool_processor.core.processor import ToolProcessor

# Create processor
processor = ToolProcessor()
await processor.initialize()

# Process text with tool calls
llm_output = """
I'll help calculate that for you.

<tool name="calculator" args='{"operation": "multiply", "x": 5, "y": 7}'/>

The result should be 35.
"""

# Extract and execute tool calls
results = await processor.process_text(llm_output)

# Process results
for result in results:
    print(f"Tool: {result.tool}")
    print(f"Result: {result.result}")
    print(f"Error: {result.error}")
```

The processor supports various formats:

```python
# XML format
<tool name="calculator" args='{"operation": "add", "x": 5, "y": 3}'/>

# OpenAI function call format
{
  "function_call": {
    "name": "calculator",
    "arguments": "{\"operation\": \"add\", \"x\": 5, \"y\": 3}"
  }
}

# JSON format
{
  "tool_calls": [
    {
      "id": "call_123",
      "type": "function",
      "function": {
        "name": "calculator",
        "arguments": "{\"operation\": \"add\", \"x\": 5, \"y\": 3}"
      }
    }
  ]
}
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.