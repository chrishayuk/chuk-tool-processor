# Getting Started

This guide walks you through creating tools and using the processor.

## Table of Contents

- [Creating Tools](#creating-tools)
  - [Simple Class-Based Tools](#simple-class-based-tools)
  - [Function-Based Tools](#function-based-tools)
  - [ValidatedTool (Pydantic)](#validatedtool-pydantic-type-safety)
  - [StreamingTool](#streamingtool-real-time-results)
- [Using the Processor](#using-the-processor)
  - [Basic Usage](#basic-usage)
  - [Production Configuration](#production-configuration)
- [Advanced Production Features](#advanced-production-features)
  - [Circuit Breaker](#circuit-breaker-pattern)
  - [Idempotency Keys](#idempotency-keys)
  - [Tool Schema Export](#tool-schema-export)
  - [Error Handling](#machine-readable-error-codes)
  - [Argument Coercion](#llm-friendly-argument-coercion)

---

## Creating Tools

CHUK Tool Processor supports multiple patterns for defining tools.

### Simple Class-Based Tools

The simplest way to create a tool:

```python
from chuk_tool_processor import tool

@tool(name="calculator")
class Calculator:
    async def execute(self, operation: str, a: float, b: float) -> dict:
        ops = {"add": a + b, "multiply": a * b, "subtract": a - b}
        return {"result": ops.get(operation, 0)}
```

### Function-Based Tools

Register a plain function as a tool:

```python
from chuk_tool_processor import register_fn_tool
from datetime import datetime
from zoneinfo import ZoneInfo

def get_current_time(timezone: str = "UTC") -> str:
    """Get the current time in the specified timezone."""
    now = datetime.now(ZoneInfo(timezone))
    return now.strftime("%Y-%m-%d %H:%M:%S %Z")

# Register the function as a tool (sync — no await needed)
register_fn_tool(get_current_time, namespace="utilities")
```

### ValidatedTool (Pydantic Type Safety)

For production tools, use Pydantic validation:

```python
from chuk_tool_processor import tool
from chuk_tool_processor.models import ValidatedTool
from pydantic import BaseModel, Field

@tool(name="weather")
class WeatherTool(ValidatedTool):
    class Arguments(BaseModel):
        location: str = Field(..., description="City name")
        units: str = Field("celsius", description="Temperature units")

    class Result(BaseModel):
        temperature: float
        conditions: str

    async def _execute(self, location: str, units: str) -> Result:
        # Your weather API logic here
        return self.Result(temperature=22.5, conditions="Sunny")
```

**Benefits of ValidatedTool:**
- Automatic argument validation
- Type coercion (string "5" → int 5)
- Whitespace stripping
- Extra fields ignored
- Clear error messages

<details>
<summary><strong>Alternative: Using @register_tool (still works)</strong></summary>

```python
from chuk_tool_processor import register_tool

@register_tool(name="weather")  # Longer form, but identical functionality
class WeatherTool(ValidatedTool):
    # ... same as above
```
</details>

### StreamingTool (Real-time Results)

For long-running operations that produce incremental results:

```python
from chuk_tool_processor import tool
from chuk_tool_processor.models import StreamingTool
from pydantic import BaseModel

@tool(name="file_processor")
class FileProcessor(StreamingTool):
    class Arguments(BaseModel):
        file_path: str

    class Result(BaseModel):
        line: int
        content: str

    async def _stream_execute(self, file_path: str):
        with open(file_path) as f:
            for i, line in enumerate(f, 1):
                yield self.Result(line=i, content=line.strip())
```

**Consuming streaming results:**

```python
import asyncio
from chuk_tool_processor import ToolProcessor, initialize

async def main():
    await initialize()
    processor = ToolProcessor()

    async for event in processor.astream(
        '<tool name="file_processor" args=\'{"file_path":"README.md"}\'/>'
    ):
        line = event.get("line") if isinstance(event, dict) else getattr(event, "line", None)
        content = event.get("content") if isinstance(event, dict) else getattr(event, "content", None)
        print(f"Line {line}: {content}")

        # Cancel after 100 lines
        if line and line > 100:
            break  # Cleanup happens automatically

asyncio.run(main())
```

---

## Using the Processor

### Basic Usage

Call `await initialize()` once at startup to load your registry. Use context managers for automatic cleanup:

```python
import asyncio
from chuk_tool_processor import ToolProcessor, initialize

async def main():
    await initialize()

    # Context manager automatically handles cleanup
    async with ToolProcessor() as processor:
        # Discover available tools
        tools = await processor.list_tools()
        print(f"Available tools: {tools}")

        # Process LLM output
        llm_output = '<tool name="calculator" args=\'{"operation":"add","a":2,"b":3}\'/>'
        results = await processor.process(llm_output)

        for result in results:
            if result.error:
                print(f"Error: {result.error}")
            else:
                print(f"Success: {result.result}")

    # Processor automatically cleaned up here!

asyncio.run(main())
```

### Production Configuration

```python
from chuk_tool_processor import ToolProcessor, initialize
import asyncio

async def main():
    await initialize()

    async with ToolProcessor(
        # Execution settings
        default_timeout=30.0,
        max_concurrency=20,

        # Production features
        enable_caching=True,
        cache_ttl=600,
        enable_rate_limiting=True,
        global_rate_limit=100,
        enable_retries=True,
        max_retries=3
    ) as processor:
        results = await processor.process(llm_output)

    # Automatic cleanup on exit

asyncio.run(main())
```

---

## Advanced Production Features

### Circuit Breaker Pattern

Prevent cascading failures by automatically opening circuits for failing tools:

```python
from chuk_tool_processor import ToolProcessor

processor = ToolProcessor(
    enable_circuit_breaker=True,
    circuit_breaker_threshold=5,      # Open after 5 failures
    circuit_breaker_timeout=60.0,     # Try recovery after 60s
)
```

**Circuit states:** `CLOSED → OPEN → HALF_OPEN → CLOSED`

| State | Behavior |
|-------|----------|
| **CLOSED** | Normal operation |
| **OPEN** | Blocking requests (too many failures) |
| **HALF_OPEN** | Testing recovery with limited requests |

**How it works:**
1. Tool fails repeatedly (hits threshold)
2. Circuit opens → requests blocked immediately
3. After timeout, circuit enters HALF_OPEN
4. If test requests succeed → circuit closes
5. If test requests fail → back to OPEN

### Idempotency Keys

Automatically deduplicate LLM tool calls using SHA256-based keys:

```python
from chuk_tool_processor.models.tool_call import ToolCall

# Idempotency keys are auto-generated
call1 = ToolCall(tool="search", arguments={"query": "Python"})
call2 = ToolCall(tool="search", arguments={"query": "Python"})

# Same arguments = same idempotency key
assert call1.idempotency_key == call2.idempotency_key

# Used automatically by caching layer
processor = ToolProcessor(enable_caching=True)
results1 = await processor.process([call1])  # Executes
results2 = await processor.process([call2])  # Cache hit!
```

**Benefits:**
- Prevents duplicate executions from LLM retries
- Deterministic cache keys
- No manual key management needed

### Tool Schema Export

Export tool definitions to multiple formats for LLM prompting:

```python
from chuk_tool_processor.models.tool_spec import ToolSpec
from chuk_tool_processor.models.validated_tool import ValidatedTool
from pydantic import BaseModel, Field

@register_tool(name="weather")
class WeatherTool(ValidatedTool):
    """Get current weather for a location."""

    class Arguments(BaseModel):
        location: str = Field(..., description="City name")

    class Result(BaseModel):
        temperature: float
        conditions: str

# Generate tool spec
spec = ToolSpec.from_validated_tool(WeatherTool)

# Export to different formats
openai_format = spec.to_openai()       # For OpenAI function calling
anthropic_format = spec.to_anthropic() # For Claude tools
mcp_format = spec.to_mcp()             # For MCP servers
```

**Example OpenAI format:**
```json
{
  "type": "function",
  "function": {
    "name": "weather",
    "description": "Get current weather for a location.",
    "parameters": {
      "type": "object",
      "properties": {
        "location": {"type": "string", "description": "City name"}
      },
      "required": ["location"]
    }
  }
}
```

### Machine-Readable Error Codes

Structured error handling with error codes for programmatic responses:

```python
from chuk_tool_processor.core.exceptions import (
    ErrorCode,
    ToolNotFoundError,
    ToolTimeoutError,
    ToolCircuitOpenError,
)

try:
    results = await processor.process(llm_output)
except ToolNotFoundError as e:
    if e.code == ErrorCode.TOOL_NOT_FOUND:
        available = e.details.get("available_tools", [])
        print(f"Try one of: {available}")
except ToolTimeoutError as e:
    if e.code == ErrorCode.TOOL_TIMEOUT:
        timeout = e.details["timeout"]
        print(f"Tool timed out after {timeout}s")
except ToolCircuitOpenError as e:
    if e.code == ErrorCode.TOOL_CIRCUIT_OPEN:
        reset_time = e.details.get("reset_timeout")
        print(f"Service unavailable, retry in {reset_time}s")

# All errors include .to_dict() for logging
error_dict = e.to_dict()
```

**Available error codes:**

| Code | Description |
|------|-------------|
| `TOOL_NOT_FOUND` | Tool doesn't exist in registry |
| `TOOL_EXECUTION_FAILED` | Tool execution error |
| `TOOL_TIMEOUT` | Tool exceeded timeout |
| `TOOL_CIRCUIT_OPEN` | Circuit breaker is open |
| `TOOL_RATE_LIMITED` | Rate limit exceeded |
| `TOOL_VALIDATION_ERROR` | Argument validation failed |
| `MCP_CONNECTION_FAILED` | MCP server unreachable |

See [ERRORS.md](ERRORS.md) for the complete error taxonomy.

### LLM-Friendly Argument Coercion

ValidatedTool automatically coerces LLM outputs to correct types:

```python
from chuk_tool_processor.models.validated_tool import ValidatedTool
from pydantic import BaseModel

class SearchTool(ValidatedTool):
    class Arguments(BaseModel):
        query: str
        limit: int = 10
        category: str = "all"

# LLM outputs often have quirks:
llm_output = {
    "query": "  Python tutorials  ",  # Extra whitespace
    "limit": "5",                      # String instead of int
    "unknown_field": "ignored"         # Extra field
}

# ValidatedTool automatically coerces and validates
tool = SearchTool()
result = await tool.execute(**llm_output)
# ✅ Works! Whitespace stripped, "5" → 5, extra field ignored
```

**Coercion features:**
- `str_strip_whitespace=True` → Remove accidental whitespace
- `extra="ignore"` → Ignore unknown fields
- `use_enum_values=True` → Convert enums to values
- Type coercion (string to int, etc.)

---

## Next Steps

- [CORE_CONCEPTS.md](CORE_CONCEPTS.md) - Understand the architecture
- [PRODUCTION_PATTERNS.md](PRODUCTION_PATTERNS.md) - Advanced patterns for production
- [ADVANCED_TOPICS.md](ADVANCED_TOPICS.md) - Isolated strategies, code sandbox, MCP
- [CONFIGURATION.md](CONFIGURATION.md) - All configuration options
