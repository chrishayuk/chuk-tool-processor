# CHUK Tool Processor

**The missing link between LLM tool calls and reliable execution.**

CHUK Tool Processor is a focused, production-ready framework that solves one problem exceptionally well: **processing tool calls from LLM outputs**. It's not a chatbot framework or LLM orchestration platform—it's the glue layer that bridges LLM responses and actual tool execution.

## The Problem

When you build LLM applications, you face a gap:

1. **LLM generates tool calls** in various formats (XML tags, OpenAI function calling, JSON)
2. **??? Mystery step ???** where you need to:
   - Parse those calls reliably
   - Handle timeouts, retries, failures
   - Cache expensive results
   - Rate limit API calls
   - Run untrusted code safely
   - Connect to external tool servers
   - Log everything for debugging
3. **Get results back** to continue the LLM conversation

Most frameworks give you step 1 and 3, but step 2 is where the complexity lives. CHUK Tool Processor **is** step 2.

## Why chuk-tool-processor?

### It's a Building Block, Not a Framework

Unlike full-fledged LLM frameworks (LangChain, LlamaIndex, etc.), CHUK Tool Processor:

- ✅ **Does one thing well**: Process tool calls reliably
- ✅ **Plugs into any LLM app**: Works with any framework or no framework
- ✅ **Composable by design**: Stack strategies and wrappers like middleware
- ✅ **No opinions about your LLM**: Bring your own OpenAI, Anthropic, local model
- ❌ **Doesn't manage conversations**: That's your job
- ❌ **Doesn't do prompt engineering**: Use whatever prompting you want
- ❌ **Doesn't bundle an LLM client**: Use any client library you prefer

### It's Built for Production

Research code vs production code is about handling the edges:

- **Timeouts**: Every tool execution has proper timeout handling
- **Retries**: Automatic retry with exponential backoff
- **Rate Limiting**: Global and per-tool rate limits with sliding windows
- **Caching**: Intelligent result caching with TTL
- **Error Handling**: Graceful degradation, never crashes your app
- **Observability**: Structured logging, metrics, request tracing
- **Safety**: Subprocess isolation for untrusted code

### It's About Stacks

CHUK Tool Processor uses a **composable stack architecture**:

```
┌─────────────────────────────────┐
│   Your LLM Application          │
│   (handles prompts, responses)  │
└────────────┬────────────────────┘
             │ tool calls
             ▼
┌─────────────────────────────────┐
│   Caching Wrapper               │  ← Cache expensive results
├─────────────────────────────────┤
│   Rate Limiting Wrapper         │  ← Prevent API abuse
├─────────────────────────────────┤
│   Retry Wrapper                 │  ← Handle transient failures
├─────────────────────────────────┤
│   Execution Strategy            │  ← How to run tools
│   • InProcess (fast)            │
│   • Subprocess (isolated)       │
├─────────────────────────────────┤
│   Tool Registry                 │  ← Your registered tools
└─────────────────────────────────┘
```

Each layer is **optional** and **configurable**. Mix and match what you need.

## Quick Start

### Installation

```bash
# Using uv (recommended)
uv pip install chuk-tool-processor

# Or from source
git clone https://github.com/chrishayuk/chuk-tool-processor.git
cd chuk-tool-processor
uv pip install -e .
```

### 3-Minute Example

```python
import asyncio
from chuk_tool_processor import ToolProcessor, register_tool, initialize

# Step 1: Define a tool
@register_tool(name="calculator")
class Calculator:
    async def execute(self, operation: str, a: float, b: float) -> dict:
        ops = {"add": a + b, "multiply": a * b, "subtract": a - b}
        return {"result": ops[operation]}

# Step 2: Process LLM output
async def main():
    await initialize()

    processor = ToolProcessor()

    # Your LLM returned this tool call
    llm_output = '<tool name="calculator" args=\'{"operation": "multiply", "a": 15, "b": 23}\'/>'

    # Process it
    results = await processor.process(llm_output)

    print(results[0].result)  # {'result': 345}

asyncio.run(main())
```

**That's it.** You now have production-ready tool execution with timeouts, retries, and caching.

### Real-World Quick Start

Here are the most common patterns you'll use:

**Pattern 1: Local tools only**
```python
from chuk_tool_processor import ToolProcessor, register_tool, initialize

@register_tool(name="my_tool")
class MyTool:
    async def execute(self, arg: str) -> dict:
        return {"result": f"Processed: {arg}"}

await initialize()
processor = ToolProcessor()
results = await processor.process(llm_output)
```

**Pattern 2: Mix local + remote MCP tools (Notion)**
```python
from chuk_tool_processor.mcp import setup_mcp_http_streamable

# Register local tools first
@register_tool(name="local_calculator")
class Calculator:
    async def execute(self, a: int, b: int) -> int:
        return a + b

# Then add remote Notion tools
processor, manager = await setup_mcp_http_streamable(
    servers=[{
        "name": "notion",
        "url": "https://mcp.notion.com/mcp",
        "headers": {"Authorization": f"Bearer {oauth_token}"}
    }],
    namespace="notion"
)

# Now you have both local and remote tools!
results = await processor.process('''
    <tool name="local_calculator" args='{"a": 5, "b": 3}'/>
    <tool name="notion.search_pages" args='{"query": "project docs"}'/>
''')
```

**Pattern 3: Local database via STDIO**
```python
from chuk_tool_processor.mcp import setup_mcp_stdio
import json

config = {
    "mcpServers": {
        "sqlite": {
            "command": "uvx",
            "args": ["mcp-server-sqlite", "--db-path", "./app.db"],
            "transport": "stdio"
        }
    }
}

with open("config.json", "w") as f:
    json.dump(config, f)

processor, manager = await setup_mcp_stdio(
    config_file="config.json",
    servers=["sqlite"],
    namespace="db"
)

# Query your database
results = await processor.process(
    '<tool name="db.query" args=\'{"sql": "SELECT * FROM users"}\'/>'
)
```

## Core Concepts

### 1. Tool Registry

The **registry** is where you register tools for execution. Tools can be:

- **Simple classes** with an `async execute()` method
- **ValidatedTool** subclasses with Pydantic validation
- **StreamingTool** for real-time incremental results
- **Functions** registered via `register_fn_tool()`

```python
from chuk_tool_processor import register_tool, ValidatedTool
from pydantic import BaseModel, Field

@register_tool(name="weather")
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

### 2. Execution Strategies

**Strategies** determine *how* tools run:

| Strategy | Use Case | Trade-offs |
|----------|----------|------------|
| **InProcessStrategy** | Fast, trusted tools | Speed ✅, Isolation ❌ |
| **SubprocessStrategy** | Untrusted or risky code | Isolation ✅, Speed ❌ |

```python
from chuk_tool_processor import ToolProcessor
from chuk_tool_processor.execution.strategies import SubprocessStrategy

processor = ToolProcessor(
    strategy=SubprocessStrategy(
        max_workers=4,
        default_timeout=30.0
    )
)
```

### 3. Execution Wrappers (Middleware)

**Wrappers** add production features as composable layers:

```python
processor = ToolProcessor(
    enable_caching=True,         # Cache expensive calls
    cache_ttl=600,               # 10 minutes
    enable_rate_limiting=True,   # Prevent abuse
    global_rate_limit=100,       # 100 req/min globally
    enable_retries=True,         # Auto-retry failures
    max_retries=3                # Up to 3 attempts
)
```

The processor stacks them automatically: **Cache → Rate Limit → Retry → Strategy → Tool**

### 4. Input Parsers (Plugins)

**Parsers** extract tool calls from various LLM output formats:

```python
# XML Tags (Anthropic-style)
'<tool name="search" args=\'{"query": "Python"}\'/>'

# OpenAI Function Calling
{"tool_calls": [{"function": {"name": "search", "arguments": '{"query": "Python"}'}}]}

# Direct JSON
[{"tool": "search", "arguments": {"query": "Python"}}]
```

All formats work automatically—no configuration needed.

### 5. MCP Integration (External Tools)

Connect to **remote tool servers** using the [Model Context Protocol](https://modelcontextprotocol.io). CHUK Tool Processor supports three transport mechanisms for different use cases:

#### HTTP Streamable (⭐ Recommended for Cloud Services)

Modern HTTP streaming transport for cloud-based MCP servers like Notion:

```python
from chuk_tool_processor.mcp import setup_mcp_http_streamable

# Connect to Notion MCP with OAuth
servers = [
    {
        "name": "notion",
        "url": "https://mcp.notion.com/mcp",
        "headers": {"Authorization": f"Bearer {your_oauth_token}"}
    }
]

processor, stream_manager = await setup_mcp_http_streamable(
    servers=servers,
    namespace="notion",
    initialization_timeout=120.0,  # Some services need time to initialize
    enable_caching=True,
    enable_retries=True
)

# Use Notion tools through MCP
results = await processor.process(
    '<tool name="notion.search_pages" args=\'{"query": "meeting notes"}\'/>'
)
```

#### STDIO (Best for Local/On-Device Tools)

For running local MCP servers as subprocesses—great for databases, file systems, and local tools:

```python
from chuk_tool_processor.mcp import setup_mcp_stdio
import json

# Configure SQLite MCP server
config = {
    "mcpServers": {
        "sqlite": {
            "command": "uvx",
            "args": ["mcp-server-sqlite", "--db-path", "/path/to/database.db"],
            "env": {"MCP_SERVER_NAME": "sqlite"},
            "transport": "stdio"
        }
    }
}

# Save config to file
with open("mcp_config.json", "w") as f:
    json.dump(config, f)

# Connect to local SQLite server
processor, stream_manager = await setup_mcp_stdio(
    config_file="mcp_config.json",
    servers=["sqlite"],
    namespace="db",
    initialization_timeout=120.0  # First run downloads packages
)

# Query your local database via MCP
results = await processor.process(
    '<tool name="db.query" args=\'{"sql": "SELECT * FROM users LIMIT 10"}\'/>'
)
```

#### SSE (Legacy Support)

For backward compatibility with older MCP servers using Server-Sent Events:

```python
from chuk_tool_processor.mcp import setup_mcp_sse

# Connect to Atlassian with OAuth via SSE
servers = [
    {
        "name": "atlassian",
        "url": "https://mcp.atlassian.com/v1/sse",
        "headers": {"Authorization": f"Bearer {oauth_token}"}
    }
]

processor, stream_manager = await setup_mcp_sse(
    servers=servers,
    namespace="atlassian",
    initialization_timeout=120.0
)
```

**Transport Comparison:**

| Transport | Use Case | Examples |
|-----------|----------|----------|
| **HTTP Streamable** | Cloud APIs, SaaS services | Notion, GitHub, modern APIs |
| **STDIO** | Local tools, databases | SQLite, filesystem, echo server |
| **SSE** | Legacy cloud services | Older MCP implementations |

**Relationship with [chuk-mcp](https://github.com/chrishayuk/chuk-mcp):**
- `chuk-mcp` is a low-level MCP protocol client (handles transports, protocol negotiation)
- `chuk-tool-processor` wraps `chuk-mcp` to integrate external tools into your execution pipeline
- You can use local tools, remote MCP tools, or both in the same processor

## Getting Started

### Creating Tools

CHUK Tool Processor supports multiple patterns for defining tools:

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

#### ValidatedTool (Pydantic Type Safety)

For production tools, use Pydantic validation:

```python
@register_tool(name="weather")
class WeatherTool(ValidatedTool):
    class Arguments(BaseModel):
        location: str = Field(..., description="City name")
        units: str = Field("celsius", description="Temperature units")

    class Result(BaseModel):
        temperature: float
        conditions: str

    async def _execute(self, location: str, units: str) -> Result:
        return self.Result(temperature=22.5, conditions="Sunny")
```

#### StreamingTool (Real-time Results)

For long-running operations that produce incremental results:

```python
from chuk_tool_processor.models import StreamingTool

@register_tool(name="file_processor")
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

### Using the Processor

#### Basic Usage

```python
from chuk_tool_processor import ToolProcessor

processor = ToolProcessor()
results = await processor.process(llm_output)

for result in results:
    if result.error:
        print(f"Error: {result.error}")
    else:
        print(f"Success: {result.result}")
```

#### Production Configuration

```python
processor = ToolProcessor(
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
)
```

## Advanced Topics

### Using Subprocess Strategy

For isolation and safety when running untrusted code:

```python
from chuk_tool_processor.execution.strategies import SubprocessStrategy

processor = ToolProcessor(
    strategy=SubprocessStrategy(
        max_workers=4,
        default_timeout=30.0
    )
)
```

### Real-World MCP Examples

#### Example 1: Notion Integration with OAuth

Complete OAuth flow connecting to Notion's MCP server:

```python
from chuk_tool_processor.mcp import setup_mcp_http_streamable

# After completing OAuth flow (see examples/notion_oauth.py for full flow)
processor, manager = await setup_mcp_http_streamable(
    servers=[{
        "name": "notion",
        "url": "https://mcp.notion.com/mcp",
        "headers": {"Authorization": f"Bearer {access_token}"}
    }],
    namespace="notion",
    initialization_timeout=120.0
)

# Get available Notion tools
tools = manager.get_all_tools()
print(f"Available tools: {[t['name'] for t in tools]}")

# Use Notion tools in your LLM workflow
results = await processor.process(
    '<tool name="notion.search_pages" args=\'{"query": "Q4 planning"}\'/>'
)
```

#### Example 2: Local SQLite Database Access

Run SQLite MCP server locally for database operations:

```python
from chuk_tool_processor.mcp import setup_mcp_stdio
import json

# Configure SQLite server
config = {
    "mcpServers": {
        "sqlite": {
            "command": "uvx",
            "args": ["mcp-server-sqlite", "--db-path", "./data/app.db"],
            "transport": "stdio"
        }
    }
}

with open("mcp_config.json", "w") as f:
    json.dump(config, f)

# Connect to local database
processor, manager = await setup_mcp_stdio(
    config_file="mcp_config.json",
    servers=["sqlite"],
    namespace="db",
    initialization_timeout=120.0  # First run downloads mcp-server-sqlite
)

# Query your database via LLM
results = await processor.process(
    '<tool name="db.query" args=\'{"sql": "SELECT COUNT(*) FROM users"}\'/>'
)
```

#### Example 3: Simple STDIO Echo Server

Minimal example for testing STDIO transport:

```python
from chuk_tool_processor.mcp import setup_mcp_stdio
import json

# Configure echo server (great for testing)
config = {
    "mcpServers": {
        "echo": {
            "command": "uvx",
            "args": ["chuk-mcp-echo", "stdio"],
            "transport": "stdio"
        }
    }
}

with open("echo_config.json", "w") as f:
    json.dump(config, f)

processor, manager = await setup_mcp_stdio(
    config_file="echo_config.json",
    servers=["echo"],
    namespace="echo",
    initialization_timeout=60.0
)

# Test echo functionality
results = await processor.process(
    '<tool name="echo.echo" args=\'{"message": "Hello MCP!"}\'/>'
)
```

See `examples/notion_oauth.py`, `examples/stdio_sqlite.py`, and `examples/stdio_echo.py` for complete working implementations.

### Structured Logging

```python
from chuk_tool_processor.logging import setup_logging

await setup_logging(
    level="INFO",
    structured=True,  # JSON output for production
    log_file="tool_processor.log"
)
```

Metrics are automatically collected for tool execution, caching, and parsing.

### Error Handling

```python
results = await processor.process(llm_output)

for result in results:
    if result.error:
        print(f"Tool '{result.tool}' failed: {result.error}")
        print(f"Duration: {result.duration}s")
    else:
        print(f"Tool '{result.tool}' succeeded: {result.result}")
```

### Testing Tools

```python
import pytest
from chuk_tool_processor import ToolProcessor, initialize

@pytest.mark.asyncio
async def test_calculator():
    await initialize()
    processor = ToolProcessor()

    results = await processor.process(
        '<tool name="calculator" args=\'{"operation": "add", "a": 5, "b": 3}\'/>'
    )

    assert results[0].result["result"] == 8
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CHUK_TOOL_REGISTRY_PROVIDER` | `memory` | Registry backend |
| `CHUK_DEFAULT_TIMEOUT` | `30.0` | Default timeout (seconds) |
| `CHUK_LOG_LEVEL` | `INFO` | Logging level |
| `CHUK_STRUCTURED_LOGGING` | `true` | Enable JSON logging |
| `MCP_BEARER_TOKEN` | - | Bearer token for MCP SSE |

### ToolProcessor Options

```python
processor = ToolProcessor(
    default_timeout=30.0,           # Timeout per tool
    max_concurrency=10,             # Max concurrent executions
    enable_caching=True,            # Result caching
    cache_ttl=300,                  # Cache TTL (seconds)
    enable_rate_limiting=False,     # Rate limiting
    enable_retries=True,            # Auto-retry failures
    max_retries=3                   # Max retry attempts
)
```

## Architecture Principles

1. **Composability**: Stack strategies and wrappers like middleware
2. **Async-First**: Built for `async/await` from the ground up
3. **Production-Ready**: Timeouts, retries, caching, rate limiting—all built-in
4. **Pluggable**: Parsers, strategies, transports—swap components as needed
5. **Observable**: Structured logging and metrics collection throughout

## Examples

Check out the [`examples/`](examples/) directory for complete working examples:

### Getting Started
- **Quick start**: `examples/quickstart_demo.py` - Basic tool registration and execution
- **Execution strategies**: `examples/execution_strategies_demo.py` - InProcess vs Subprocess
- **Production wrappers**: `examples/wrappers_demo.py` - Caching, retries, rate limiting
- **Streaming tools**: `examples/streaming_demo.py` - Real-time incremental results

### MCP Integration (Real-World)
- **Notion + OAuth**: `examples/notion_oauth.py` - Complete OAuth 2.1 flow with HTTP Streamable
  - Shows: Authorization Server discovery, client registration, PKCE flow, token exchange
- **SQLite Local**: `examples/stdio_sqlite.py` - Local database access via STDIO
  - Shows: Command/args passing, environment variables, file paths, initialization timeouts
- **Echo Server**: `examples/stdio_echo.py` - Minimal STDIO transport example
  - Shows: Simplest possible MCP integration for testing
- **Atlassian + OAuth**: `examples/atlassian_sse.py` - OAuth with SSE transport (legacy)

### Advanced MCP
- **HTTP Streamable**: `examples/mcp_http_streamable_example.py`
- **STDIO**: `examples/mcp_stdio_example.py`
- **SSE**: `examples/mcp_sse_example.py`
- **Plugin system**: `examples/plugins_builtins_demo.py`, `examples/plugins_custom_parser_demo.py`

## Related Projects

- **[chuk-mcp](https://github.com/chrishayuk/chuk-mcp)**: Low-level Model Context Protocol client
  - Powers the MCP transport layer in chuk-tool-processor
  - Use directly if you need protocol-level control
  - Use chuk-tool-processor if you want high-level tool execution

## Contributing & Support

- **GitHub**: [chrishayuk/chuk-tool-processor](https://github.com/chrishayuk/chuk-tool-processor)
- **Issues**: [Report bugs and request features](https://github.com/chrishayuk/chuk-tool-processor/issues)
- **Discussions**: [Community discussions](https://github.com/chrishayuk/chuk-tool-processor/discussions)
- **License**: MIT

---

**Remember**: CHUK Tool Processor is the missing link between LLM outputs and reliable tool execution. It's not trying to be everything—it's trying to be the best at one thing: processing tool calls in production.

Built with ❤️ by the CHUK AI team for the LLM tool integration community.