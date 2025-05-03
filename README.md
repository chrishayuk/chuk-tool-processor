# CHUK Tool Processor

A robust framework for detecting, executing, and managing tool calls in LLM responses.

## Overview

The CHUK Tool Processor is a Python library designed to handle the execution of tools referenced in the output of Large Language Models (LLMs). It provides a flexible and extensible architecture for:

1. **Parsing tool calls** from different formats (JSON, XML, function calls)
2. **Executing tools** with proper isolation and error handling
3. **Managing tool executions** with retry logic, caching, and rate limiting
4. **Monitoring tool usage** with comprehensive logging
5. **MCP (Model Context Protocol) Integration** for remote tool execution

## Features

- **Multiple Parser Support**: Extract tool calls from JSON, XML, or OpenAI-style function call formats
- **Flexible Execution Strategies**: Choose between in-process or subprocess execution for different isolation needs
- **Namespace Support**: Organize tools in logical namespaces
- **Concurrency Control**: Set limits on parallel tool executions
- **Validation**: Type validation for tool arguments and results
- **Caching**: Cache tool results to improve performance for repeated calls
- **Rate Limiting**: Prevent overloading external services with configurable rate limits
- **Retry Logic**: Automatically retry transient failures with exponential backoff
- **Structured Logging**: Comprehensive logging system for debugging and monitoring
- **Plugin Discovery**: Dynamically discover and load plugins from packages
- **MCP Integration**: Connect to and execute remote tools via Model Context Protocol

## Installation

```bash
# Clone the repository
git clone https://github.com/your-org/chuk-tool-processor.git
cd chuk-tool-processor

# Install with pip
pip install -e .

# Or with uv
uv pip install -e .
```

## Quick Start

### Registering Tools

```python
from chuk_tool_processor.registry import register_tool

@register_tool(name="calculator", namespace="math")
class CalculatorTool:
    def execute(self, operation: str, a: float, b: float):
        if operation == "add":
            return a + b
        elif operation == "multiply":
            return a * b
        # ... other operations
```

### Processing Tool Calls

```python
import asyncio
from chuk_tool_processor.core.processor import ToolProcessor

async def main():
    # Create a processor with default settings
    processor = ToolProcessor()
    
    # Process text with potential tool calls
    llm_response = """
    To calculate that, I'll use the calculator tool.
    
    {
      "function_call": {
        "name": "calculator",
        "arguments": {"operation": "multiply", "a": 123.45, "b": 67.89}
      }
    }
    """
    
    results = await processor.process_text(llm_response)
    
    # Handle results
    for result in results:
        print(f"Tool: {result.tool}")
        print(f"Result: {result.result}")
        print(f"Error: {result.error}")
        print(f"Duration: {(result.end_time - result.start_time).total_seconds()}s")

if __name__ == "__main__":
    asyncio.run(main())
```

## MCP Integration

The CHUK Tool Processor supports Model Context Protocol (MCP) for connecting to remote tool servers. This enables distributed tool execution and integration with third-party services.

### MCP with Stdio Transport

```python
import asyncio
from chuk_tool_processor.mcp import setup_mcp_stdio

async def main():
    # Configure MCP server
    config_file = "server_config.json"
    servers = ["echo", "calculator", "search"]
    server_names = {0: "echo", 1: "calculator", 2: "search"}
    
    # Setup MCP with stdio transport
    processor, stream_manager = await setup_mcp_stdio(
        config_file=config_file,
        servers=servers,
        server_names=server_names,
        namespace="mcp",  # All tools will be registered under this namespace
        enable_caching=True,
        enable_retries=True
    )
    
    # Process text with MCP tool calls
    llm_text = """
    Let me echo your message using the MCP server.
    
    <tool name="mcp.echo" args='{"message": "Hello from MCP!"}'/>
    """
    
    results = await processor.process_text(llm_text)
    
    for result in results:
        print(f"Tool: {result.tool}")
        print(f"Result: {result.result}")
    
    # Clean up
    await stream_manager.close()

if __name__ == "__main__":
    asyncio.run(main())
```

### MCP Server Configuration

Create a server configuration file (`server_config.json`):

```json
{
  "mcpServers": {
    "echo": {
      "command": "uv",
      "args": ["--directory", "/path/to/echo-server", "run", "src/echo_server/main.py"]
    },
    "calculator": {
      "command": "node",
      "args": ["/path/to/calculator-server/index.js"]
    },
    "search": {
      "command": "python",
      "args": ["/path/to/search-server/main.py"]
    }
  }
}
```

### Namespaced Tool Access

MCP tools are automatically registered in both their namespace and the default namespace:

```python
# These are equivalent:
<tool name="echo" args='{"message": "Hello"}'/>
<tool name="mcp.echo" args='{"message": "Hello"}'/>
```

### MCP with SSE Transport

```python
import asyncio
from chuk_tool_processor.mcp import setup_mcp_sse

async def main():
    # Configure SSE servers
    sse_servers = [
        {
            "name": "weather",
            "url": "https://api.example.com/sse/weather",
            "api_key": "your_api_key"
        },
        {
            "name": "geocoding",
            "url": "https://api.example.com/sse/geocoding"
        }
    ]
    
    # Setup MCP with SSE transport
    processor, stream_manager = await setup_mcp_sse(
        servers=sse_servers,
        server_names={0: "weather", 1: "geocoding"},
        namespace="remote",
        enable_caching=True
    )
    
    # Process tool calls
    llm_text = """
    Get the weather for New York.
    
    <tool name="remote.weather" args='{"location": "New York", "units": "imperial"}'/>
    """
    
    results = await processor.process_text(llm_text)
    
    await stream_manager.close()
```

### MCP Stream Manager

The `StreamManager` class handles all MCP communication:

```python
from chuk_tool_processor.mcp.stream_manager import StreamManager

# Create and initialize
stream_manager = await StreamManager.create(
    config_file="config.json",
    servers=["echo", "search"],
    transport_type="stdio"
)

# Get available tools
tools = stream_manager.get_all_tools()
for tool in tools:
    print(f"Tool: {tool['name']}")

# Get server information
server_info = stream_manager.get_server_info()
for server in server_info:
    print(f"Server: {server['name']}, Status: {server['status']}")

# Call a tool directly
result = await stream_manager.call_tool(
    tool_name="echo",
    arguments={"message": "Hello"}
)

# Clean up
await stream_manager.close()
```

## Advanced Usage

### Using Decorators for Tool Configuration

```python
from chuk_tool_processor.registry import register_tool
from chuk_tool_processor.utils.validation import with_validation
from chuk_tool_processor.execution.wrappers.retry import retryable
from chuk_tool_processor.execution.wrappers.caching import cacheable
from chuk_tool_processor.execution.wrappers.rate_limiting import rate_limited
from typing import Dict, Any, Optional

@register_tool(name="weather", namespace="data")
@retryable(max_retries=3)
@cacheable(ttl=3600)  # Cache for 1 hour
@rate_limited(limit=100, period=60.0)  # 100 requests per minute
@with_validation
class WeatherTool:
    def execute(self, location: str, units: str = "metric") -> Dict[str, Any]:
        # Implementation that calls a weather API
        return {
            "temperature": 22.5,
            "conditions": "Partly Cloudy",
            "humidity": 65
        }
```

### Using Validated Tool Base Class

```python
from chuk_tool_processor.utils.validation import ValidatedTool
from chuk_tool_processor.registry import register_tool
from pydantic import BaseModel
from typing import Optional

@register_tool(namespace="data")
class WeatherTool(ValidatedTool):
    class Arguments(BaseModel):
        location: str
        units: str = "metric"  # Default to metric
    
    class Result(BaseModel):
        temperature: float
        conditions: str
        humidity: Optional[int] = None
    
    def _execute(self, location: str, units: str = "metric"):
        # Implementation
        return {
            "temperature": 22.5,
            "conditions": "Sunny",
            "humidity": 65
        }
```

### Custom Execution Strategy

```python
from chuk_tool_processor.registry.providers.memory import InMemoryToolRegistry
from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.execution.inprocess_strategy import InProcessStrategy

# Create registry and register tools
registry = InMemoryToolRegistry()
registry.register_tool(MyTool(), name="my_tool")

# Create executor with custom strategy
executor = ToolExecutor(
    registry,
    strategy=InProcessStrategy(
        registry,
        default_timeout=5.0,
        max_concurrency=10
    )
)

# Execute tool calls
results = await executor.execute([call1, call2])
```

### Custom Parser Plugins

```python
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.plugins.discovery import plugin_registry
import re
from typing import List

# Create a custom parser for a bracket syntax
class BracketToolParser:
    """Parser for [tool:name arg1=val1 arg2="val2"] syntax"""
    
    def try_parse(self, raw: str) -> List[ToolCall]:
        calls = []
        # Regex to match [tool:name arg1=val1 arg2="val2"]
        pattern = r"\[tool:([^\s\]]+)([^\]]*)\]"
        matches = re.finditer(pattern, raw)
        
        for match in matches:
            tool_name = match.group(1)
            args_str = match.group(2).strip()
            
            # Parse arguments
            args = {}
            if args_str:
                # Match key=value pairs, handling quoted values
                args_pattern = r'([^\s=]+)=(?:([^\s"]+)|"([^"]*)")'
                for arg_match in re.finditer(args_pattern, args_str):
                    key = arg_match.group(1)
                    # Either group 2 (unquoted) or group 3 (quoted)
                    value = arg_match.group(2) if arg_match.group(2) else arg_match.group(3)
                    args[key] = value
            
            calls.append(ToolCall(tool=tool_name, arguments=args))
        
        return calls

# Register plugin manually
plugin_registry.register_plugin("parser", "BracketToolParser", BracketToolParser())
```

### Structured Logging

```python
from chuk_tool_processor.logging import get_logger, log_context_span

logger = get_logger("my_module")

# Create a context span for timing operations
with log_context_span("operation_name", {"extra": "context"}):
    logger.info("Starting operation")
    # Do something
    logger.info("Operation completed")
```

## Architecture

The tool processor has several key components organized into a modular structure:

1. **Registry**: Stores tool implementations and metadata
   - `registry/interface.py`: Defines the registry interface
   - `registry/providers/memory.py`: In-memory implementation
   - `registry/providers/redis.py`: Redis-backed implementation

2. **Models**: Core data structures
   - `models/tool_call.py`: Represents a tool call from an LLM
   - `models/tool_result.py`: Represents the result of a tool execution

3. **Execution**: Tool execution strategies and wrappers
   - `execution/tool_executor.py`: Main executor interface
   - `execution/inprocess_strategy.py`: Same-process execution
   - `execution/subprocess_strategy.py`: Isolated process execution
   - `execution/wrappers/`: Enhanced executors (caching, retries, etc.)

4. **Plugins**: Extensible plugin system
   - `plugins/discovery.py`: Plugin discovery mechanism
   - `plugins/parsers/`: Parser plugins for different formats

5. **MCP Integration**: Model Context Protocol support
   - `mcp/stream_manager.py`: Manages MCP server connections
   - `mcp/transport/`: Transport implementations (stdio, SSE)
   - `mcp/setup_mcp_*.py`: Easy setup functions for MCP integration

6. **Utils**: Shared utilities
   - `utils/logging.py`: Structured logging system
   - `utils/validation.py`: Argument and result validation

7. **Core**: Central components
   - `core/processor.py`: Main processor for handling tool calls
   - `core/exceptions.py`: Exception hierarchy

## Examples

The repository includes several example scripts:

- `examples/tool_registry_example.py`: Demonstrates tool registration and usage
- `examples/plugin_example.py`: Shows how to create and use custom plugins
- `examples/tool_calling_example_usage.py`: Basic example demonstrating tool execution
- `examples/mcp_stdio_example.py`: MCP stdio transport demonstration
- `examples/mcp_stdio_example_calling_usage.py`: Complete MCP integration example

Run examples with:

```bash
# Registry example
uv run examples/tool_registry_example.py

# Plugin example
uv run examples/plugin_example.py

# Tool execution example
uv run examples/tool_calling_example_usage.py

# MCP example
uv run examples/mcp_stdio_example.py

# Enable debug logging
LOGLEVEL=DEBUG uv run examples/tool_calling_example_usage.py
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.