# CHUK Tool Processor — Production-grade execution for LLM tool calls

[![PyPI](https://img.shields.io/pypi/v/chuk-tool-processor.svg)](https://pypi.org/project/chuk-tool-processor/)
[![Python](https://img.shields.io/pypi/pyversions/chuk-tool-processor.svg)](https://pypi.org/project/chuk-tool-processor/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Type Checked](https://img.shields.io/badge/type%20checked-PEP%20561-blue.svg)](https://www.python.org/dev/peps/pep-0561/)
[![Wheels](https://img.shields.io/badge/wheels-macOS%20%7C%20Linux%20%7C%20Windows-blue.svg)](https://pypi.org/project/chuk-tool-processor/)
[![OpenTelemetry](https://img.shields.io/badge/observability-OpenTelemetry%20%7C%20Prometheus-blue.svg)](docs/OBSERVABILITY.md)

**Reliable tool execution for LLMs — timeouts, retries, caching, rate limits, circuit breakers, and MCP integration — in one composable layer.**

---

## The Missing Layer for Reliable Tool Execution

LLMs are good at *calling* tools. The hard part is **executing** those tools reliably.

**CHUK Tool Processor:**
- Parses tool calls from any model (Anthropic XML, OpenAI `tool_calls`, JSON)
- Executes them with **timeouts, retries, caching, rate limits, circuit breaker, observability**
- Runs tools locally, in **isolated subprocesses**, or **remote via MCP**

CHUK Tool Processor is the execution layer between LLM responses and real tools.

It sits **below** agent frameworks and prompt orchestration, and **above** raw tool implementations.

```
    LLM Output
        ↓
CHUK Tool Processor
        ↓
 ┌──────────────┬────────────────────┐
 │ Local Tools  │ Remote Tools (MCP) │
 └──────────────┴────────────────────┘
```

**How it works internally:**

```
    LLM Output
        ↓
Parsers (XML / OpenAI / JSON)
        ↓
┌─────────────────────────────┐
│   Execution Middleware      │
│  (Applied in this order)    │
│   • Cache                   │
│   • Rate Limit              │
│   • Retry (with backoff)    │
│   • Circuit Breaker         │
└─────────────────────────────┘
        ↓
   Execution Strategy
   ┌──────────────────────┐
   │ • InProcess          │  ← Fast, trusted
   │ • Isolated/Subprocess│  ← Safe, untrusted
   │ • Remote via MCP     │  ← Distributed
   └──────────────────────┘
```

Works with OpenAI, Anthropic, local models (Ollama/MLX/vLLM), and any framework (LangChain, LlamaIndex, custom).

## Executive TL;DR

* **Parse any format:** `XML` (Anthropic), `OpenAI tool_calls`, or raw `JSON`
* **Execute with production policies:** timeouts/retries/cache/rate-limits/circuit-breaker/idempotency
* **Run anywhere:** locally (fast), isolated (subprocess sandbox), or remote via MCP (HTTP/STDIO/SSE)

```python
import asyncio
from chuk_tool_processor import ToolProcessor, tool

@tool(name="weather")  # Clean decorator syntax
class WeatherTool:
    async def execute(self, city: str) -> dict:
        return {"temp": 72, "condition": "sunny", "city": city}

async def main():
    # No need for initialize() - auto-initializes on first use!
    async with ToolProcessor(enable_caching=True, enable_retries=True) as p:
        # Works with OpenAI, Anthropic, or JSON formats
        result = await p.process('<tool name="weather" args=\'{"city": "SF"}\'/>')
        print(result[0].result)  # {'temp': 72, 'condition': 'sunny', 'city': 'SF'}

asyncio.run(main())
```

> **If you only remember three things:**
>
> 1. **Parse** `XML`, `OpenAI tool_calls`, or raw `JSON` automatically
> 2. **Execute** with timeouts/retries/cache/rate-limits/circuit-breaker
> 3. **Run** tools locally, isolated (subprocess), or remote via MCP

## When to Use This

Use **CHUK Tool Processor** when:
- Your LLM calls tools or APIs
- You need **retries, timeouts, caching, or rate limits**
- You need to **run untrusted tools safely**
- Your tools are **local or remote (MCP)**

Do **not** use this if:
- You want an agent framework
- You want conversation flow/memory orchestration

**This is the execution layer, not the agent.**

> **Not a framework.**
> If LangChain/LlamaIndex help decide *which* tool to call,
> CHUK Tool Processor makes sure the tool call **actually succeeds**.

## Table of Contents

- [The Problem](#the-problem)
- [Why chuk-tool-processor?](#why-chuk-tool-processor)
- [Compatibility Matrix](#compatibility-matrix)
- [Developer Experience Highlights](#developer-experience-highlights)
- [Quick Start](#quick-start)
- [Documentation Quick Reference](#documentation-quick-reference)
- [Choose Your Path](#choose-your-path)
- [Core Concepts](#core-concepts)
- [Getting Started](#getting-started)
- [Advanced Topics](#advanced-topics)
- [Configuration](#configuration)
- [Architecture Principles](#architecture-principles)
- [Examples](#examples)
- [FAQ](#faq)
- [Comparison with Other Tools](#comparison-with-other-tools)
- [Development & Publishing](#development--publishing)
- [Stability & Versioning](#stability--versioning)
- [Contributing & Support](#contributing--support)

## The Problem

LLMs generate tool calls. **The hard part is executing them reliably.**

CHUK Tool Processor **is that execution layer.**

## Why chuk-tool-processor?

**Composable execution layers:**

```
┌─────────────────────────────────┐
│   Your LLM Application          │
│   (handles prompts, responses)  │
└────────────┬────────────────────┘
             │ tool calls
             ▼
┌─────────────────────────────────┐
│   Caching Wrapper               │  ← Cache expensive results (idempotency keys)
├─────────────────────────────────┤
│   Rate Limiting Wrapper         │  ← Prevent API abuse
├─────────────────────────────────┤
│   Retry Wrapper                 │  ← Handle transient failures (exponential backoff)
├─────────────────────────────────┤
│   Circuit Breaker Wrapper       │  ← Prevent cascading failures (CLOSED/OPEN/HALF_OPEN)
├─────────────────────────────────┤
│   Execution Strategy            │  ← How to run tools
│   • InProcess (fast)            │
│   • Isolated (subprocess)       │
├─────────────────────────────────┤
│   Tool Registry                 │  ← Your registered tools
└─────────────────────────────────┘
```

Each layer is **optional** and **configurable**. Mix and match what you need.

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

Research code vs production code is about handling the edges. CHUK Tool Processor includes:

- ✅ **Timeouts** — Every tool execution has proper timeout handling
- ✅ **Retries** — Automatic retry with exponential backoff and deadline awareness
- ✅ **Rate Limiting** — Global and per-tool rate limits with sliding windows → [CONFIGURATION.md](docs/CONFIGURATION.md)
- ✅ **Caching** — Intelligent result caching with TTL and idempotency key support
- ✅ **Circuit Breakers** — Prevent cascading failures with automatic fault detection
- ✅ **Idempotency** — SHA256-based deduplication of LLM retry quirks
- ✅ **Error Handling** — Machine-readable error codes with structured details → [ERRORS.md](docs/ERRORS.md)
- ✅ **Observability** — Structured logging, metrics, OpenTelemetry tracing → [OBSERVABILITY.md](docs/OBSERVABILITY.md)
- ✅ **Safety** — Subprocess isolation for untrusted code (zero crash blast radius)
- ✅ **Type Safety** — PEP 561 compliant with full mypy support
- ✅ **Resource Management** — Context managers for automatic cleanup
- ✅ **Tool Discovery** — Formal schema export (OpenAI, Anthropic, MCP formats)
- ✅ **Cancellation** — Cooperative cancellation with request-scoped deadlines

## Compatibility Matrix

Runs the same on macOS, Linux, and Windows — locally, serverside, and inside containers.

| Component | Supported Versions | Notes |
|-----------|-------------------|-------|
| **Python** | 3.11, 3.12, 3.13 | Python 3.11+ required |
| **Operating Systems** | macOS, Linux, Windows | All platforms fully supported |
| **LLM Providers** | OpenAI, Anthropic, Local models | Any LLM that outputs tool calls |
| **MCP Transports** | HTTP Streamable, STDIO, SSE | All MCP 1.0 transports |
| **MCP Servers** | Notion, SQLite, Atlassian, Echo, Custom | Any MCP-compliant server |

**Tested Configurations:**
- ✅ macOS 14+ (Apple Silicon & Intel)
- ✅ Ubuntu 20.04+ / Debian 11+
- ✅ Windows 10+ (native & WSL2)
- ✅ Python 3.11.0+, 3.12.0+, 3.13.0+
- ✅ OpenAI GPT-4, GPT-4 Turbo
- ✅ Anthropic Claude 3 (Opus, Sonnet, Haiku)
- ✅ Local models (Ollama, LM Studio)

## Developer Experience Highlights

**What makes CHUK Tool Processor easy to use:**

* **Auto-parsing**: XML (Claude), OpenAI `tool_calls`, direct JSON—all work automatically
* **One call**: `process()` handles multiple calls & formats in a single invocation
* **Auto-coercion**: Pydantic-powered argument cleanup (whitespace, type conversion, extra fields ignored)
* **Safe defaults**: timeouts, retries, caching toggles built-in
* **Observability in one line**: `setup_observability(...)` for traces + metrics
* **MCP in one call**: `setup_mcp_http_streamable|stdio|sse(...)` connects to remote tools instantly
* **Context managers**: `async with ToolProcessor() as p:` ensures automatic cleanup
* **Full type safety**: PEP 561 compliant—mypy, pyright, and IDEs get complete type information

## Quick Start

### Installation

**Prerequisites:** Python 3.11+ • Works on macOS, Linux, Windows

```bash
# Using pip
pip install chuk-tool-processor

# Using uv (recommended)
uv pip install chuk-tool-processor
```

<details>
<summary><strong>Install from source or with extras</strong></summary>

```bash
# From source
git clone https://github.com/chrishayuk/chuk-tool-processor.git
cd chuk-tool-processor
uv pip install -e .

# With observability extras (OpenTelemetry + Prometheus)
pip install chuk-tool-processor[observability]

# With MCP extras
pip install chuk-tool-processor[mcp]

# With fast JSON serialization (2-3x faster, recommended for production)
pip install chuk-tool-processor[fast-json]

# All extras
pip install chuk-tool-processor[all]
```

</details>

<details>
<summary><strong>Performance Optimization (Optional)</strong></summary>

For **2-3x faster JSON operations**, install with the `fast-json` extra:

```bash
pip install chuk-tool-processor[fast-json]
```

This installs [orjson](https://github.com/ijl/orjson), a fast C-based JSON library. When available, it's automatically used for JSON serialization/deserialization throughout the processor while maintaining full compatibility with stdlib json.

**Benchmarks** (see `benchmarks/` for full results):

| Operation | stdlib json | orjson | Speedup |
|-----------|-------------|--------|---------|
| Simple JSON (100 bytes) | 1.23 µs | 0.45 µs | **2.7x faster** |
| Complex JSON (5 KB) | 12.5 µs | 4.2 µs | **3.0x faster** |
| OpenAI tool calls | 8.9 µs | 3.1 µs | **2.9x faster** |

**Notes:**
- Falls back to stdlib json automatically if orjson is not installed
- Hash computation uses stdlib json for consistency across environments
- No code changes required—just install the extra

</details>

<details>
<summary><strong>Type Checking Support (PEP 561 compliant)</strong></summary>

CHUK Tool Processor includes **full type checking support**:

```python
# mypy, pyright, and IDEs get full type information!
from chuk_tool_processor import ToolProcessor, ToolCall, ToolResult

async with ToolProcessor() as processor:
    # Full autocomplete and type checking
    results: list[ToolResult] = await processor.process(llm_output)
    tools: list[str] = await processor.list_tools()
```

**Features:**
- ✅ `py.typed` marker for PEP 561 compliance
- ✅ Comprehensive type hints on all public APIs
- ✅ Works with mypy, pyright, pylance
- ✅ Full IDE autocomplete support

**No special mypy configuration needed** - just import and use!

</details>

## 60-Second Quick Start

### From raw LLM output to safe execution in 3 lines

```python
from chuk_tool_processor import ToolProcessor, initialize

await initialize()
async with ToolProcessor() as p:
    results = await p.process('<tool name="calculator" args=\'{"operation":"multiply","a":15,"b":23}\'/>')
```

**Note:** This assumes you've registered a "calculator" tool. See complete example below.

### Works with Both OpenAI and Anthropic (No Adapters Needed)

```python
from chuk_tool_processor import ToolProcessor, register_tool, initialize

@register_tool(name="search")
class SearchTool:
    async def execute(self, query: str) -> dict:
        return {"results": [f"Found: {query}"]}

await initialize()
async with ToolProcessor() as p:
    # OpenAI format
    openai_response = {"tool_calls": [{"type": "function", "function": {"name": "search", "arguments": '{"query": "Python"}'}}]}

    # Anthropic format
    anthropic_response = '<tool name="search" args=\'{"query": "Python"}\'/>'

    # Both work identically
    results_openai = await p.process(openai_response)
    results_anthropic = await p.process(anthropic_response)
```

**Absolutely minimal example** → See `examples/01_getting_started/hello_tool.py`:

```bash
python examples/01_getting_started/hello_tool.py
```

Single file that demonstrates:
- Registering a tool
- Parsing OpenAI & Anthropic formats
- Executing and getting results

Takes 60 seconds to understand, 3 minutes to master.

### 3-Minute Example

Copy-paste this into a file and run it:

```python
import asyncio
from chuk_tool_processor import ToolProcessor, tool

# Step 1: Define a tool with the clean @tool decorator
@tool(name="calculator")
class Calculator:
    async def execute(self, operation: str, a: float, b: float) -> dict:
        ops = {"add": a + b, "multiply": a * b, "subtract": a - b}
        if operation not in ops:
            raise ValueError(f"Unsupported operation: {operation}")
        return {"result": ops[operation]}

# Step 2: Process LLM output
async def main():
    # No initialize() needed - it auto-initializes!

    # Use context manager for automatic cleanup
    async with ToolProcessor() as processor:
        # Your LLM returned this tool call
        llm_output = '<tool name="calculator" args=\'{"operation": "multiply", "a": 15, "b": 23}\'/>'

        # Process it
        results = await processor.process(llm_output)

        # Each result is a ToolResult with: tool, result, error, duration, cached
        if results[0].error:
            print(f"Error: {results[0].error}")
        else:
            print(results[0].result)  # {'result': 345}

    # Processor automatically cleaned up!

asyncio.run(main())
```

**That's it.** You now have production-ready tool execution with:
- ✅ Automatic timeouts, retries, and caching
- ✅ Clean resource management (context manager)
- ✅ Full type checking support
- ✅ Auto-initialization (no boilerplate!)

> **Why not just use OpenAI tool calls?**
> OpenAI's function calling is great for parsing, but you still need: parsing multiple formats (Anthropic XML, etc.), timeouts, retries, rate limits, caching, subprocess isolation, connecting to external MCP servers, and **per-tool** policy control with cross-provider parsing and MCP fan-out. CHUK Tool Processor **is** that missing middle layer.

### Enhanced Developer Experience

CHUK Tool Processor provides intuitive APIs and helpful error messages:

**1. Clean Decorator Syntax**
```python
from chuk_tool_processor import tool

@tool(name="calculator")  # Short and clean!
class Calculator:
    async def execute(self, a: int, b: int) -> int:
        return a + b
```

**2. Auto-Initialization (No Boilerplate)**
```python
from chuk_tool_processor import ToolProcessor

# No initialize() needed - it auto-initializes!
async with ToolProcessor() as p:
    results = await p.process(llm_output)
```

**3. Type-Safe Tool Discovery**
```python
from chuk_tool_processor import get_default_registry, ToolInfo

registry = await get_default_registry()

# List all registered tools with clear, typed results
tools = await registry.list_tools()
for tool in tools:  # Each tool is a ToolInfo object
    print(f"{tool.namespace}:{tool.name}")  # Clear attribute access!
    # No more confusing tuple unpacking: (namespace, name) vs (name, namespace)?
```

**4. Helpful Error Messages**
```python
# Typo in tool name? Get helpful suggestions!
try:
    await registry.get_tool_strict("calcuator", namespace="default")
except Exception as e:
    print(e)
    # Output:
    # Tool 'calcuator' not found in namespace 'default'
    #
    # Did you mean: calculator?
    #
    # Available namespaces: default, math, mcp
    #
    # Tip: Use `await registry.list_tools()` to see all registered tools
```

**5. Clean MCP Configuration**
```python
from chuk_tool_processor.mcp import setup_mcp_stdio, MCPConfig, MCPServerConfig

# Clean Pydantic config object instead of 14+ parameters!
processor, manager = await setup_mcp_stdio(
    config=MCPConfig(
        servers=[MCPServerConfig(name="echo", command="uvx", args=["mcp-echo"])],
        namespace="tools",
        enable_caching=True,
        cache_ttl=600,
    )
)
```

**Key improvements:**
- ✅ **`@tool` decorator**: Shorter, cleaner than `@register_tool`
- ✅ **Auto-initialization**: No need for explicit `initialize()` calls
- ✅ **Type-safe tool listing**: `ToolInfo` objects instead of confusing tuples
- ✅ **Helpful errors**: Fuzzy matching suggestions when tools aren't found
- ✅ **MCPConfig**: Clean Pydantic model instead of 14+ parameters
- ✅ **Better discoverability**: Clear guidance on how to explore available tools

## Quick Decision Tree (Commit This to Memory)

```
╭──────────────────────────────────────────╮
│ Do you trust the code you're executing?  │
│   ✅ Yes → InProcessStrategy              │
│   ⚠️ No → IsolatedStrategy (sandboxed)     │
│                                          │
│ Where do your tools live?                │
│   📦 Local → @tool decorator              │
│   🌐 Remote → setup_mcp_* with MCPConfig  │
╰──────────────────────────────────────────╯
```

**That's all you need to pick the right pattern.**

## Registry & Processor Lifecycle

Understanding the lifecycle helps you use CHUK Tool Processor correctly:

1. **Auto-initialization** — Registry auto-initializes on first access (or call `await initialize()` explicitly)
2. Create a **`ToolProcessor(...)`** (or use the one returned by `setup_mcp_*`)
3. Use **`async with ToolProcessor() as p:`** to ensure cleanup
4. **`setup_mcp_*`** returns `(processor, manager)` — reuse that `processor`
5. If you need a custom registry, pass it explicitly to the strategy
6. You rarely need `get_default_registry()` unless you're composing advanced setups

**New in this version:** The registry auto-initializes when you create a `ToolProcessor` or access `get_default_registry()`, so you can skip the explicit `initialize()` call in most cases!

```python
# New simplified pattern (auto-initialization)
async with ToolProcessor() as p:  # Auto-initializes on first use!
    results = await p.process(llm_output)
    # Processor automatically cleaned up on exit

# Traditional explicit pattern (still works)
await initialize()  # Explicit initialization
async with ToolProcessor() as p:
    results = await p.process(llm_output)
```

## Production Features by Example

### Idempotency & Deduplication

Automatically deduplicate LLM retry quirks using SHA256-based idempotency keys:

```python
from chuk_tool_processor import ToolProcessor, initialize

await initialize()
async with ToolProcessor(enable_caching=True, cache_ttl=300) as p:
    # LLM retries the same call (common with streaming or errors)
    call1 = '<tool name="search" args=\'{"query": "Python"}\'/>'
    call2 = '<tool name="search" args=\'{"query": "Python"}\'/>'  # Identical

    results1 = await p.process(call1)  # Executes
    results2 = await p.process(call2)  # Cache hit! (idempotency key match)

    assert results1[0].cached == False
    assert results2[0].cached == True
```

### Cancellation & Deadlines

Cooperative cancellation with request-scoped deadlines:

```python
import asyncio
from chuk_tool_processor import ToolProcessor, initialize

async def main():
    await initialize()
    async with ToolProcessor(default_timeout=60.0) as p:
        try:
            # Hard deadline for the whole batch (e.g., user request budget)
            async with asyncio.timeout(5.0):
                async for event in p.astream('<tool name="slow_report" args=\'{"n": 1000000}\'/>'):
                    print("chunk:", event)
        except TimeoutError:
            print("Request cancelled: deadline exceeded")
            # Processor automatically cancels the tool and cleans up

asyncio.run(main())
```

### Per-Tool Policy Overrides

Override timeouts, retries, and rate limits per tool:

```python
from chuk_tool_processor import ToolProcessor, initialize

await initialize()
async with ToolProcessor(
    default_timeout=30.0,
    enable_retries=True,
    max_retries=2,
    enable_rate_limiting=True,
    global_rate_limit=120,  # 120 requests/min across all tools
    tool_rate_limits={
        "expensive_api": (5, 60),  # 5 requests per 60 seconds
        "fast_local": (1000, 60),  # 1000 requests per 60 seconds
    }
) as p:
    # Tools run with their specific policies
    results = await p.process('''
        <tool name="expensive_api" args='{"q":"abc"}'/>
        <tool name="fast_local" args='{"data":"xyz"}'/>
    ''')
```

## Documentation Quick Reference

| Document | What It Covers |
|----------|----------------|
| 📘 [CONFIGURATION.md](docs/CONFIGURATION.md) | **All config knobs & defaults**: ToolProcessor options, timeouts, retry policy, rate limits, circuit breakers, caching, environment variables |
| 🚨 [ERRORS.md](docs/ERRORS.md) | **Error taxonomy**: All error codes, exception classes, error details structure, handling patterns, retryability guide |
| 📊 [OBSERVABILITY.md](docs/OBSERVABILITY.md) | **Metrics & tracing**: OpenTelemetry setup, Prometheus metrics, spans reference, PromQL queries |
| 🔌 [examples/01_getting_started/hello_tool.py](examples/01_getting_started/hello_tool.py) | **60-second starter**: Single-file, copy-paste-and-run example |
| 🎯 [examples/](examples/) | **20+ working examples**: MCP integration, OAuth flows, streaming, production patterns |

## Choose Your Path

**Use this when OpenAI/Claude tool calling is not enough** — because you need retries, caching, rate limits, subprocess isolation, or MCP integration.

| Your Goal | What You Need | Where to Look |
|-----------|---------------|---------------|
| ☕ **Just process LLM tool calls** | Basic tool registration + processor | [60-Second Quick Start](#60-second-quick-start) |
| 🔌 **Connect to external tools** | MCP integration (HTTP/STDIO/SSE) | [MCP Integration](#5-mcp-integration-external-tools) |
| 🛡️ **Production deployment** | Timeouts, retries, rate limits, caching | [CONFIGURATION.md](docs/CONFIGURATION.md) |
| 🔒 **Run untrusted code safely** | Isolated strategy (subprocess) | [Isolated Strategy](#using-isolated-strategy) |
| 📊 **Monitor and observe** | OpenTelemetry + Prometheus | [OBSERVABILITY.md](docs/OBSERVABILITY.md) |
| 🌊 **Stream incremental results** | StreamingTool pattern | [StreamingTool](#streamingtool-real-time-results) |
| 🚨 **Handle errors reliably** | Error codes & taxonomy | [ERRORS.md](docs/ERRORS.md) |

### Real-World Quick Start

Here are the most common patterns you'll use:

**Pattern 1: Local tools only**
```python
import asyncio
from chuk_tool_processor import ToolProcessor, register_tool, initialize

@register_tool(name="my_tool")
class MyTool:
    async def execute(self, arg: str) -> dict:
        return {"result": f"Processed: {arg}"}

async def main():
    await initialize()

    async with ToolProcessor() as processor:
        llm_output = '<tool name="my_tool" args=\'{"arg": "hello"}\'/>'
        results = await processor.process(llm_output)
        print(results[0].result)  # {'result': 'Processed: hello'}

asyncio.run(main())
```

<details>
<summary><strong>More patterns: MCP integration (local + remote tools)</strong></summary>

**Pattern 2: Mix local + remote MCP tools (Notion)**
```python
import asyncio
from chuk_tool_processor import register_tool, initialize, setup_mcp_http_streamable

@register_tool(name="local_calculator")
class Calculator:
    async def execute(self, a: int, b: int) -> int:
        return a + b

async def main():
    # Register local tools first
    await initialize()

    # Then add Notion MCP tools (requires OAuth token)
    processor, manager = await setup_mcp_http_streamable(
        servers=[{
            "name": "notion",
            "url": "https://mcp.notion.com/mcp",
            "headers": {"Authorization": f"Bearer {access_token}"}
        }],
        namespace="notion",
        initialization_timeout=120.0
    )

    # Now you have both local and remote tools!
    results = await processor.process('''
        <tool name="local_calculator" args='{"a": 5, "b": 3}'/>
        <tool name="notion.search_pages" args='{"query": "project docs"}'/>
    ''')
    print(f"Local result: {results[0].result}")
    print(f"Notion result: {results[1].result}")

    # Clean up
    await manager.close()

asyncio.run(main())
```

See `examples/04_mcp_integration/notion_oauth.py` for complete OAuth flow.

**Pattern 3: Local SQLite database via STDIO (New Clean API)**
```python
import asyncio
from chuk_tool_processor.mcp import setup_mcp_stdio, MCPConfig, MCPServerConfig

async def main():
    # NEW: Clean Pydantic config approach (recommended!)
    processor, manager = await setup_mcp_stdio(
        config=MCPConfig(
            servers=[
                MCPServerConfig(
                    name="sqlite",
                    command="uvx",
                    args=["mcp-server-sqlite", "--db-path", "./app.db"],
                )
            ],
            namespace="db",
            initialization_timeout=120.0,  # First run downloads the package
            enable_caching=True,
            cache_ttl=600,
        )
    )

    # Query your local database via MCP
    results = await processor.process(
        '<tool name="db.query" args=\'{"sql": "SELECT * FROM users LIMIT 10"}\'/>'
    )
    print(results[0].result)

asyncio.run(main())
```

<details>
<summary><strong>Legacy approach (still works)</strong></summary>

```python
import asyncio
import json
from chuk_tool_processor.mcp import setup_mcp_stdio

async def main():
    # Configure SQLite MCP server (runs locally)
    config = {
        "mcpServers": {
            "sqlite": {
                "command": "uvx",
                "args": ["mcp-server-sqlite", "--db-path", "./app.db"],
                "transport": "stdio"
            }
        }
    }

    with open("mcp_config.json", "w") as f:
        json.dump(config, f)

    processor, manager = await setup_mcp_stdio(
        config_file="mcp_config.json",
        servers=["sqlite"],
        namespace="db",
        initialization_timeout=120.0
    )

    # Query your local database via MCP
    results = await processor.process(
        '<tool name="db.query" args=\'{"sql": "SELECT * FROM users LIMIT 10"}\'/>'
    )
    print(results[0].result)

asyncio.run(main())
```
</details>

See `examples/04_mcp_integration/stdio_sqlite.py` for complete working example.

</details>

## Core Concepts

### 1. Tool Registry

The **registry** is where you register tools for execution. Tools can be:

- **Simple classes** with an `async execute()` method
- **ValidatedTool** subclasses with Pydantic validation
- **StreamingTool** for real-time incremental results
- **Functions** registered via `register_fn_tool()`

> **Note:** The registry is global, processors are scoped.

```python
from chuk_tool_processor import register_tool
from chuk_tool_processor.models.validated_tool import ValidatedTool
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
| **IsolatedStrategy** | Untrusted or risky code | Isolation ✅, Speed ❌ |

```python
import asyncio
from chuk_tool_processor import ToolProcessor, IsolatedStrategy, get_default_registry

async def main():
    registry = await get_default_registry()
    processor = ToolProcessor(
        strategy=IsolatedStrategy(
            registry=registry,
            max_workers=4,
            default_timeout=30.0
        )
    )
    # Use processor...

asyncio.run(main())
```

**Note:** `IsolatedStrategy` is an alias of `SubprocessStrategy` for backwards compatibility. Use `IsolatedStrategy` for clarity—it better communicates the security boundary intent.

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

**XML Tags (Anthropic-style)**
```xml
<tool name="search" args='{"query": "Python"}'/>
```

**OpenAI `tool_calls` (JSON)**
```json
{
  "tool_calls": [
    {
      "type": "function",
      "function": {
        "name": "search",
        "arguments": "{\"query\": \"Python\"}"
      }
    }
  ]
}
```

**Direct JSON (array of calls)**
```json
[
  { "tool": "search", "arguments": { "query": "Python" } }
]
```

All formats work automatically—no configuration needed.

**Input Format Compatibility:**

| Format | Example | Use Case |
|--------|---------|----------|
| **XML Tool Tag** | `<tool name="search" args='{"q":"Python"}'/>`| Anthropic Claude, XML-based LLMs |
| **OpenAI tool_calls** | JSON object (above) | OpenAI GPT-4 function calling |
| **Direct JSON** | `[{"tool": "search", "arguments": {"q": "Python"}}]` | Generic API integrations |
| **Single dict** | `{"tool": "search", "arguments": {"q": "Python"}}` | Programmatic calls |

### 5. MCP Integration (External Tools)

Connect to **remote tool servers** using the [Model Context Protocol](https://modelcontextprotocol.io). CHUK Tool Processor supports three transport mechanisms for different use cases:

#### HTTP Streamable (⭐ Recommended for Cloud Services)

**Use for:** Cloud SaaS services (OAuth, long-running streams, resilient reconnects)

Modern HTTP streaming transport for cloud-based MCP servers like Notion:

```python
from chuk_tool_processor.mcp import setup_mcp_http_streamable

# Connect to Notion MCP with OAuth
servers = [
    {
        "name": "notion",
        "url": "https://mcp.notion.com/mcp",
        "headers": {"Authorization": f"Bearer {access_token}"}
    }
]

processor, manager = await setup_mcp_http_streamable(
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

<details>
<summary><strong>Other MCP Transports (STDIO for local tools, SSE for legacy)</strong></summary>

#### STDIO (Best for Local/On-Device Tools)

**Use for:** Local/embedded tools and databases (SQLite, file systems, local services)

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
processor, manager = await setup_mcp_stdio(
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

**Use for:** Legacy compatibility only. Prefer HTTP Streamable for new integrations.

For backward compatibility with older MCP servers using Server-Sent Events:

```python
from chuk_tool_processor.mcp import setup_mcp_sse

# Connect to Atlassian with OAuth via SSE
servers = [
    {
        "name": "atlassian",
        "url": "https://mcp.atlassian.com/v1/sse",
        "headers": {"Authorization": f"Bearer {access_token}"}
    }
]

processor, manager = await setup_mcp_sse(
    servers=servers,
    namespace="atlassian",
    initialization_timeout=120.0
)
```

</details>

**Transport Comparison:**

| Transport | Use Case | Real Examples |
|-----------|----------|---------------|
| **HTTP Streamable** | Cloud APIs, SaaS services | Notion (`mcp.notion.com`) |
| **STDIO** | Local tools, databases | SQLite (`mcp-server-sqlite`), Echo (`chuk-mcp-echo`) |
| **SSE** | Legacy cloud services | Atlassian (`mcp.atlassian.com`) |

**How MCP fits into the architecture:**

```
    LLM Output
        ↓
  Tool Processor
        ↓
 ┌──────────────┬────────────────────┐
 │ Local Tools  │ Remote Tools (MCP) │
 └──────────────┴────────────────────┘
```

**Relationship with [chuk-mcp](https://github.com/chrishayuk/chuk-mcp):**
- `chuk-mcp` is a low-level MCP protocol client (handles transports, protocol negotiation)
- `chuk-tool-processor` wraps `chuk-mcp` to integrate external tools into your execution pipeline
- You can use local tools, remote MCP tools, or both in the same processor

## Getting Started

### Creating Tools

CHUK Tool Processor supports multiple patterns for defining tools:

#### Simple Function-Based Tools
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

#### ValidatedTool (Pydantic Type Safety)

For production tools, use Pydantic validation:

```python
from chuk_tool_processor import tool
from chuk_tool_processor.models import ValidatedTool
from pydantic import BaseModel, Field

@tool(name="weather")  # Clean @tool decorator
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

<details>
<summary><strong>Alternative: Using @register_tool (still works)</strong></summary>

```python
from chuk_tool_processor import register_tool

@register_tool(name="weather")  # Longer form, but identical functionality
class WeatherTool(ValidatedTool):
    # ... same as above
```
</details>

#### StreamingTool (Real-time Results)

For long-running operations that produce incremental results:

```python
from chuk_tool_processor import tool
from chuk_tool_processor.models import StreamingTool
from pydantic import BaseModel

@tool(name="file_processor")  # Clean @tool decorator
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

    # Stream can be cancelled by breaking or raising an exception
    try:
        async for event in processor.astream('<tool name="file_processor" args=\'{"file_path":"README.md"}\'/>'):
            # 'event' is a streamed chunk (either your Result model instance or a dict)
            line = event["line"] if isinstance(event, dict) else getattr(event, "line", None)
            content = event["content"] if isinstance(event, dict) else getattr(event, "content", None)
            print(f"Line {line}: {content}")

            # Example: cancel after 100 lines
            if line and line > 100:
                break  # Cleanup happens automatically
    except asyncio.CancelledError:
        # Stream cleanup is automatic even on cancellation
        pass

asyncio.run(main())
```

### Using the Processor

#### Basic Usage

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

#### Production Configuration

```python
from chuk_tool_processor import ToolProcessor, initialize
import asyncio

async def main():
    await initialize()

    # Use context manager with production config
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
        # Use processor...
        results = await processor.process(llm_output)

    # Automatic cleanup on exit

asyncio.run(main())
```

### Advanced Production Features

Beyond basic configuration, CHUK Tool Processor includes several advanced features for production environments:

#### Circuit Breaker Pattern

Prevent cascading failures by automatically opening circuits for failing tools:

```python
from chuk_tool_processor import ToolProcessor

processor = ToolProcessor(
    enable_circuit_breaker=True,
    circuit_breaker_threshold=5,      # Open after 5 failures
    circuit_breaker_timeout=60.0,     # Try recovery after 60s
)

# Circuit states: CLOSED → OPEN → HALF_OPEN → CLOSED
# - CLOSED: Normal operation
# - OPEN: Blocking requests (too many failures)
# - HALF_OPEN: Testing recovery with limited requests
```

**How it works:**
1. Tool fails repeatedly (hits threshold)
2. Circuit opens → requests blocked immediately
3. After timeout, circuit enters HALF_OPEN
4. If test requests succeed → circuit closes
5. If test requests fail → back to OPEN

**Benefits:**
- Prevents wasting resources on failing services
- Fast-fail for better UX
- Automatic recovery detection

#### Idempotency Keys

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

**Cache scope:** In-memory per-process by default. Cache backend is pluggable—see [CONFIGURATION.md](docs/CONFIGURATION.md) for custom cache backends.

#### Tool Schema Export

Export tool definitions to multiple formats for LLM prompting:

```python
from chuk_tool_processor.models.tool_spec import ToolSpec, ToolCapability
from chuk_tool_processor.models.validated_tool import ValidatedTool

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

# Example OpenAI format:
# {
#   "type": "function",
#   "function": {
#     "name": "weather",
#     "description": "Get current weather for a location.",
#     "parameters": {...}  # JSON Schema
#   }
# }
```

**Use cases:**
- Generate tool definitions for LLM system prompts
- Documentation generation
- API contract validation
- Cross-platform tool sharing

#### Machine-Readable Error Codes

Structured error handling with error codes for programmatic responses.

**Error Contract:** Every error includes a machine-readable code, human-readable message, and structured details:

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
        # Suggest available tools to LLM
        available = e.details.get("available_tools", [])
        print(f"Try one of: {available}")
except ToolTimeoutError as e:
    if e.code == ErrorCode.TOOL_TIMEOUT:
        # Inform LLM to use faster alternative
        timeout = e.details["timeout"]
        print(f"Tool timed out after {timeout}s")
except ToolCircuitOpenError as e:
    if e.code == ErrorCode.TOOL_CIRCUIT_OPEN:
        # Tell LLM this service is temporarily down
        reset_time = e.details.get("reset_timeout")
        print(f"Service unavailable, retry in {reset_time}s")

# All errors include .to_dict() for logging
error_dict = e.to_dict()
# {
#   "error": "ToolCircuitOpenError",
#   "code": "TOOL_CIRCUIT_OPEN",
#   "message": "Tool 'api_tool' circuit breaker is open...",
#   "details": {"tool_name": "api_tool", "failure_count": 5, ...}
# }
```

**Available error codes:**
- `TOOL_NOT_FOUND` - Tool doesn't exist in registry
- `TOOL_EXECUTION_FAILED` - Tool execution error
- `TOOL_TIMEOUT` - Tool exceeded timeout
- `TOOL_CIRCUIT_OPEN` - Circuit breaker is open
- `TOOL_RATE_LIMITED` - Rate limit exceeded
- `TOOL_VALIDATION_ERROR` - Argument validation failed
- `MCP_CONNECTION_FAILED` - MCP server unreachable
- Plus 11 more for comprehensive error handling

#### LLM-Friendly Argument Coercion

Automatically coerce LLM outputs to correct types:

```python
from chuk_tool_processor.models.validated_tool import ValidatedTool

class SearchTool(ValidatedTool):
    class Arguments(BaseModel):
        query: str
        limit: int = 10
        category: str = "all"

    # Pydantic config for LLM outputs:
    # - str_strip_whitespace=True    → Remove accidental whitespace
    # - extra="ignore"               → Ignore unknown fields
    # - use_enum_values=True         → Convert enums to values
    # - coerce_numbers_to_str=False  → Keep type strictness

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

## Advanced Topics

### Using Isolated Strategy

Use `IsolatedStrategy` when running untrusted, third-party, or potentially unsafe code that shouldn't share the same process as your main app.

For isolation and safety when running untrusted code:

```python
import asyncio
from chuk_tool_processor import ToolProcessor, IsolatedStrategy, get_default_registry

async def main():
    registry = await get_default_registry()
    processor = ToolProcessor(
        strategy=IsolatedStrategy(
            registry=registry,
            max_workers=4,
            default_timeout=30.0
        )
    )
    # Use processor...

asyncio.run(main())
```

> **Security & Isolation — Threat Model**
>
> Untrusted tool code runs in subprocesses; faults and crashes don't bring down your app. **Zero crash blast radius.** For hard CPU/RAM/network limits, run the processor inside a container with `--cpus`, `--memory`, and egress filtering. Secrets are never injected by default—pass them explicitly via tool arguments or scoped environment variables.

### Real-World MCP Examples

#### Example 1: Notion Integration with OAuth

Complete OAuth flow connecting to Notion's MCP server:

```python
from chuk_tool_processor.mcp import setup_mcp_http_streamable

# After completing OAuth flow (see examples/04_mcp_integration/notion_oauth.py for full flow)
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

<details>
<summary><strong>Click to expand more MCP examples (SQLite, Echo Server)</strong></summary>

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

</details>

See `examples/04_mcp_integration/notion_oauth.py`, `examples/04_mcp_integration/stdio_sqlite.py`, and `examples/04_mcp_integration/stdio_echo.py` for complete working implementations.

#### OAuth Token Refresh

<details>
<summary><strong>Click to expand OAuth token refresh guide</strong></summary>

For MCP servers that use OAuth authentication, CHUK Tool Processor supports automatic token refresh when access tokens expire. This prevents your tools from failing due to expired tokens during long-running sessions.

**How it works:**
1. When a tool call receives an OAuth-related error (e.g., "invalid_token", "expired token", "unauthorized")
2. The processor automatically calls your refresh callback
3. Updates the authentication headers with the new token
4. Retries the tool call with fresh credentials

**Setup with HTTP Streamable:**

```python
from chuk_tool_processor.mcp import setup_mcp_http_streamable

async def refresh_oauth_token():
    """Called automatically when tokens expire."""
    # Your token refresh logic here
    # Return dict with new Authorization header
    new_token = await your_refresh_logic()
    return {"Authorization": f"Bearer {new_token}"}

processor, manager = await setup_mcp_http_streamable(
    servers=[{
        "name": "notion",
        "url": "https://mcp.notion.com/mcp",
        "headers": {"Authorization": f"Bearer {initial_access_token}"}
    }],
    namespace="notion",
    oauth_refresh_callback=refresh_oauth_token  # Enable auto-refresh
)
```

**Setup with SSE:**

```python
from chuk_tool_processor.mcp import setup_mcp_sse

async def refresh_oauth_token():
    """Refresh expired OAuth token."""
    # Exchange refresh token for new access token
    new_access_token = await exchange_refresh_token(refresh_token)
    return {"Authorization": f"Bearer {new_access_token}"}

processor, manager = await setup_mcp_sse(
    servers=[{
        "name": "atlassian",
        "url": "https://mcp.atlassian.com/v1/sse",
        "headers": {"Authorization": f"Bearer {initial_token}"}
    }],
    namespace="atlassian",
    oauth_refresh_callback=refresh_oauth_token
)
```

**OAuth errors detected automatically:**
- `invalid_token`
- `expired token`
- `OAuth validation failed`
- `unauthorized`
- `token expired`
- `authentication failed`
- `invalid access token`

**Important notes:**
- The refresh callback must return a dict with an `Authorization` key
- If refresh fails or returns invalid headers, the original error is returned
- Token refresh is attempted only once per tool call (no infinite retry loops)
- After successful refresh, the updated headers are used for all subsequent calls

See `examples/04_mcp_integration/notion_oauth.py` for a complete OAuth 2.1 implementation with PKCE and automatic token refresh.

</details>

### Observability

#### Structured Logging

Enable JSON logging for production observability:

```python
import asyncio
from chuk_tool_processor.logging import setup_logging, get_logger

async def main():
    await setup_logging(
        level="INFO",
        structured=True,  # JSON output (structured=False for human-readable)
        log_file="tool_processor.log"
    )
    logger = get_logger("my_app")
    logger.info("logging ready")

asyncio.run(main())
```

When `structured=True`, logs are output as JSON. When `structured=False`, they're human-readable text.

Example JSON log output:

```json
{
  "timestamp": "2025-01-15T10:30:45.123Z",
  "level": "INFO",
  "tool": "calculator",
  "status": "success",
  "duration_ms": 4.2,
  "cached": false,
  "attempts": 1
}
```

#### Automatic Metrics

Metrics are automatically collected for:
- ✅ Tool execution (success/failure rates, duration)
- ✅ Cache performance (hit/miss rates)
- ✅ Parser accuracy (which parsers succeeded)
- ✅ Retry attempts (how many retries per tool)

Access metrics programmatically:

```python
import asyncio
from chuk_tool_processor.logging import metrics

async def main():
    # Metrics are logged automatically, but you can also access them
    await metrics.log_tool_execution(
        tool="custom_tool",
        success=True,
        duration=1.5,
        cached=False,
        attempts=1
    )

asyncio.run(main())
```

#### OpenTelemetry & Prometheus (Drop-in Observability)

<details>
<summary><strong>Click to expand complete observability guide</strong></summary>

**3-Line Setup:**

```python
from chuk_tool_processor.observability import setup_observability

setup_observability(
    service_name="my-tool-service",
    enable_tracing=True,     # → OpenTelemetry traces
    enable_metrics=True,     # → Prometheus metrics at :9090/metrics
    metrics_port=9090
)
# That's it! Every tool execution is now automatically traced and metered.
```

**What you get automatically:**
- ✅ Distributed traces (Jaeger, Zipkin, any OTLP collector)
- ✅ Prometheus metrics (error rate, latency P50/P95/P99, cache hit rate)
- ✅ Circuit breaker state monitoring
- ✅ Retry attempt tracking
- ✅ Zero code changes to your tools

**Why Telemetry Matters**: In production, you need to know *what* your tools are doing, *how long* they take, *when* they fail, and *why*. CHUK Tool Processor provides **enterprise-grade telemetry** that operations teams expect—with zero manual instrumentation.

**What You Get (Automatically)**

✅ **Distributed Traces** - Understand exactly what happened in each tool call
- See the complete execution timeline for every tool
- Track retries, cache hits, circuit breaker state changes
- Correlate failures across your system
- Export to Jaeger, Zipkin, or any OTLP-compatible backend

✅ **Production Metrics** - Monitor health and performance in real-time
- Track error rates, latency percentiles (P50/P95/P99)
- Monitor cache hit rates and retry attempts
- Alert on circuit breaker opens and rate limit hits
- Export to Prometheus, Grafana, or any metrics backend

✅ **Zero Configuration** - Works out of the box
- No manual instrumentation needed
- No code changes to existing tools
- Gracefully degrades if packages not installed
- Standard OTEL and Prometheus formats

**Installation**

```bash
# Install observability dependencies
pip install chuk-tool-processor[observability]

# Or manually
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp prometheus-client

# Or with uv (recommended)
uv pip install chuk-tool-processor --group observability
```

> **⚠️ SRE Note**: Observability packages are **optional**. If not installed, all observability calls are no-ops—your tools run normally without tracing/metrics. Zero crashes, zero warnings. Safe to deploy without observability dependencies.

**Quick Start: See Your Tools in Action**

```python
import asyncio
from chuk_tool_processor.observability import setup_observability
from chuk_tool_processor import ToolProcessor, initialize, register_tool

@register_tool(name="weather_api")
class WeatherTool:
    async def execute(self, location: str) -> dict:
        # Simulating API call
        return {"temperature": 72, "conditions": "sunny", "location": location}

async def main():
    # 1. Enable observability (one line!)
    setup_observability(
        service_name="weather-service",
        enable_tracing=True,
        enable_metrics=True,
        metrics_port=9090
    )

    # 2. Create processor with production features
    await initialize()
    processor = ToolProcessor(
        enable_caching=True,         # Cache expensive API calls
        enable_retries=True,         # Auto-retry on failures
        enable_circuit_breaker=True, # Prevent cascading failures
        enable_rate_limiting=True,   # Prevent API abuse
    )

    # 3. Execute tools - automatically traced and metered
    results = await processor.process(
        '<tool name="weather_api" args=\'{"location": "San Francisco"}\'/>'
    )

    print(f"Result: {results[0].result}")
    print(f"Duration: {results[0].duration}s")
    print(f"Cached: {results[0].cached}")

asyncio.run(main())
```

**View Your Data**

```bash
# Start Jaeger for trace visualization
docker run -d -p 4317:4317 -p 16686:16686 jaegertracing/all-in-one:latest

# Start your application
python your_app.py

# View distributed traces
open http://localhost:16686

# View Prometheus metrics
curl http://localhost:9090/metrics | grep tool_
```

**What Gets Traced (Automatic Spans)**

Every execution layer creates standardized OpenTelemetry spans:

| Span Name | When Created | Key Attributes |
|-----------|--------------|----------------|
| `tool.execute` | Every tool execution | `tool.name`, `tool.namespace`, `tool.duration_ms`, `tool.cached`, `tool.error`, `tool.success` |
| `tool.cache.lookup` | Cache lookup | `cache.hit` (true/false), `cache.operation=lookup` |
| `tool.cache.set` | Cache write | `cache.ttl`, `cache.operation=set` |
| `tool.retry.attempt` | Each retry | `retry.attempt`, `retry.max_attempts`, `retry.success` |
| `tool.circuit_breaker.check` | Circuit state check | `circuit.state` (CLOSED/OPEN/HALF_OPEN) |
| `tool.rate_limit.check` | Rate limit check | `rate_limit.allowed` (true/false) |

**Example trace hierarchy:**
```
tool.execute (weather_api)
├── tool.cache.lookup (miss)
├── tool.retry.attempt (0)
│   └── tool.execute (actual API call)
├── tool.retry.attempt (1) [if first failed]
└── tool.cache.set (store result)
```

**What Gets Metered (Automatic Metrics)**

Standard Prometheus metrics exposed at `/metrics`:

| Metric | Type | Labels | Use For |
|--------|------|--------|---------|
| `tool_executions_total` | Counter | `tool`, `namespace`, `status` | Error rate, request volume |
| `tool_execution_duration_seconds` | Histogram | `tool`, `namespace` | P50/P95/P99 latency |
| `tool_cache_operations_total` | Counter | `tool`, `operation`, `result` | Cache hit rate |
| `tool_retry_attempts_total` | Counter | `tool`, `attempt`, `success` | Retry frequency |
| `tool_circuit_breaker_state` | Gauge | `tool` | Circuit health (0=CLOSED, 1=OPEN, 2=HALF_OPEN) |
| `tool_circuit_breaker_failures_total` | Counter | `tool` | Failure count |
| `tool_rate_limit_checks_total` | Counter | `tool`, `allowed` | Rate limit hits |

**Useful PromQL Queries**

```promql
# Error rate per tool (last 5 minutes)
rate(tool_executions_total{status="error"}[5m])
/ rate(tool_executions_total[5m])

# P95 latency
histogram_quantile(0.95, rate(tool_execution_duration_seconds_bucket[5m]))

# Cache hit rate
rate(tool_cache_operations_total{result="hit"}[5m])
/ rate(tool_cache_operations_total{operation="lookup"}[5m])

# Tools currently circuit broken
tool_circuit_breaker_state == 1

# Retry rate (how often tools need retries)
rate(tool_retry_attempts_total{attempt!="0"}[5m])
/ rate(tool_executions_total[5m])
```

**Configuration**

Configure via environment variables:

```bash
# OTLP endpoint (where traces are sent)
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317

# Service name (shown in traces)
export OTEL_SERVICE_NAME=production-api

# Sampling (reduce overhead in high-traffic scenarios)
export OTEL_TRACES_SAMPLER=traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1  # Sample 10% of traces
```

Or in code:

```python
status = setup_observability(
    service_name="my-service",
    enable_tracing=True,
    enable_metrics=True,
    metrics_port=9090,
    metrics_host="0.0.0.0"  # Allow external Prometheus scraping
)

# Check status
if status["tracing_enabled"]:
    print("Traces exporting to OTLP endpoint")
if status["metrics_server_started"]:
    print("Metrics available at http://localhost:9090/metrics")
```

**Production Integration**

**With Grafana + Prometheus:**
```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'chuk-tool-processor'
    scrape_interval: 15s
    static_configs:
      - targets: ['app:9090']
```

**With OpenTelemetry Collector:**
```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

exporters:
  jaeger:
    endpoint: jaeger:14250
  prometheus:
    endpoint: 0.0.0.0:8889

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [jaeger]
```

**With Cloud Providers:**
```bash
# AWS X-Ray
export OTEL_TRACES_SAMPLER=xray

# Google Cloud Trace
export OTEL_EXPORTER_OTLP_ENDPOINT=https://cloudtrace.googleapis.com/v1/projects/PROJECT_ID/traces

# Datadog
export OTEL_EXPORTER_OTLP_ENDPOINT=http://datadog-agent:4317
```

**Why This Matters**

❌ **Without telemetry:**
- "Why is this tool slow?" → No idea
- "Is caching helping?" → Guessing
- "Did that retry work?" → Check logs manually
- "Is the circuit breaker working?" → Hope so
- "Which tool is failing?" → Debug blindly

✅ **With telemetry:**
- See exact execution timeline in Jaeger
- Monitor cache hit rate in Grafana
- Alert when retry rate spikes
- Dashboard shows circuit breaker states
- Metrics pinpoint the failing tool immediately

**Learn More**

📖 **Complete Guide**: See [`OBSERVABILITY.md`](OBSERVABILITY.md) for:
- Complete span and metric specifications
- Architecture and implementation details
- Integration guides (Jaeger, Grafana, OTEL Collector)
- Testing observability features
- Environment variable configuration

🎯 **Working Example**: See `examples/02_production_features/observability_demo.py` for a complete demonstration with retries, caching, and circuit breakers

**Benefits**

✅ **Drop-in** - One function call, zero code changes
✅ **Automatic** - All execution layers instrumented
✅ **Standard** - OTEL + Prometheus (works with existing tools)
✅ **Production-ready** - Ops teams get exactly what they expect
✅ **Optional** - Gracefully degrades if packages not installed
✅ **Zero-overhead** - No performance impact when disabled

</details>

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

**Fake tool pattern for testing:**

```python
import pytest
from chuk_tool_processor import ToolProcessor, register_tool, initialize

@register_tool(name="fake_tool")
class FakeTool:
    """No-op tool for testing processor behavior."""
    call_count = 0

    async def execute(self, **kwargs) -> dict:
        FakeTool.call_count += 1
        return {"called": True, "args": kwargs}

@pytest.mark.asyncio
async def test_processor_with_fake_tool():
    await initialize()
    processor = ToolProcessor()

    # Reset counter
    FakeTool.call_count = 0

    # Execute fake tool
    results = await processor.process(
        '<tool name="fake_tool" args=\'{"test_arg": "value"}\'/>'
    )

    # Assert behavior
    assert FakeTool.call_count == 1
    assert results[0].result["called"] is True
    assert results[0].result["args"]["test_arg"] == "value"
```

## Configuration

### Timeout Configuration

CHUK Tool Processor uses a unified timeout configuration system that applies to all MCP transports (HTTP Streamable, SSE, STDIO) and the StreamManager. Instead of managing dozens of individual timeout values, there are just **4 logical timeout categories**:

```python
from chuk_tool_processor.mcp.transport import TimeoutConfig

# Create custom timeout configuration
# (Defaults are: connect=30, operation=30, quick=5, shutdown=2)
timeout_config = TimeoutConfig(
    connect=30.0,     # Connection establishment, initialization, session discovery
    operation=30.0,   # Normal operations (tool calls, listing tools/resources/prompts)
    quick=5.0,        # Fast health checks and pings
    shutdown=2.0      # Cleanup and shutdown operations
)
```

**Using timeout configuration with StreamManager:**

```python
from chuk_tool_processor.mcp.stream_manager import StreamManager
from chuk_tool_processor.mcp.transport import TimeoutConfig

# Create StreamManager with custom timeouts
timeout_config = TimeoutConfig(
    connect=60.0,     # Longer for slow initialization
    operation=45.0,   # Longer for heavy operations
    quick=3.0,        # Faster health checks
    shutdown=5.0      # More time for cleanup
)

manager = StreamManager(timeout_config=timeout_config)
```

**Timeout categories explained:**

| Category | Default | Used For | Examples |
|----------|---------|----------|----------|
| `connect` | 30.0s | Connection setup, initialization, discovery | HTTP connection, SSE session discovery, STDIO subprocess launch |
| `operation` | 30.0s | Normal tool operations | Tool calls, listing tools/resources/prompts, get_tools() |
| `quick` | 5.0s | Fast health/status checks | Ping operations, health checks |
| `shutdown` | 2.0s | Cleanup and teardown | Transport close, connection cleanup |

**Why this matters:**
- ✅ **Simple**: 4 timeout values instead of 20+
- ✅ **Consistent**: Same timeout behavior across all transports
- ✅ **Configurable**: Adjust timeouts based on your environment (slow networks, large datasets, etc.)
- ✅ **Type-safe**: Pydantic validation ensures correct values

**Example: Adjusting for slow environments**

```python
from chuk_tool_processor.mcp import setup_mcp_stdio
from chuk_tool_processor.mcp.transport import TimeoutConfig

# For slow network or resource-constrained environments
slow_timeouts = TimeoutConfig(
    connect=120.0,    # Allow more time for package downloads
    operation=60.0,   # Allow more time for heavy operations
    quick=10.0,       # Be patient with health checks
    shutdown=10.0     # Allow thorough cleanup
)

processor, manager = await setup_mcp_stdio(
    config_file="mcp_config.json",
    servers=["sqlite"],
    namespace="db",
    initialization_timeout=120.0
)

# Set custom timeouts on the manager
manager.timeout_config = slow_timeouts
```

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
    global_rate_limit=None,         # (requests per minute) global cap
    enable_retries=True,            # Auto-retry failures
    max_retries=3,                  # Max retry attempts
    # Optional per-tool rate limits: {"tool.name": (requests, per_seconds)}
    tool_rate_limits=None
)
```

### Performance & Tuning

| Parameter | Default | When to Adjust |
|-----------|---------|----------------|
| `default_timeout` | `30.0` | Increase for slow tools (e.g., AI APIs) |
| `max_concurrency` | `10` | Increase for I/O-bound tools, decrease for CPU-bound |
| `enable_caching` | `True` | Keep on for deterministic tools |
| `cache_ttl` | `300` | Longer for stable data, shorter for real-time |
| `enable_rate_limiting` | `False` | Enable when hitting API rate limits |
| `global_rate_limit` | `None` | Set a global requests/min cap across all tools |
| `enable_retries` | `True` | Disable for non-idempotent operations |
| `max_retries` | `3` | Increase for flaky external APIs |
| `tool_rate_limits` | `None` | Dict mapping tool name → (max_requests, window_seconds). Overrides `global_rate_limit` per tool |

**Per-tool rate limiting example:**

```python
processor = ToolProcessor(
    enable_rate_limiting=True,
    global_rate_limit=100,  # 100 requests/minute across all tools
    tool_rate_limits={
        "notion.search_pages": (10, 60),  # 10 requests per 60 seconds
        "expensive_api": (5, 60),          # 5 requests per minute
        "local_tool": (1000, 60),          # 1000 requests per minute (local is fast)
    }
)
```

### Security Model

CHUK Tool Processor provides multiple layers of safety:

| Concern | Protection | Configuration |
|---------|------------|---------------|
| **Timeouts** | Every tool has a timeout | `default_timeout=30.0` |
| **Process Isolation** | Run tools in separate processes | `strategy=IsolatedStrategy()` |
| **Rate Limiting** | Prevent abuse and API overuse | `enable_rate_limiting=True` |
| **Input Validation** | Pydantic validation on arguments | Use `ValidatedTool` |
| **Error Containment** | Failures don't crash the processor | Built-in exception handling |
| **Retry Limits** | Prevent infinite retry loops | `max_retries=3` |

**Important Security Notes:**
- **Environment Variables**: Subprocess strategy inherits the parent process environment by default. For stricter isolation, use container-level controls (Docker, cgroups).
- **Network Access**: Tools inherit network access from the host. For network isolation, use OS-level sandboxing (containers, network namespaces, firewalls).
- **Resource Limits**: For hard CPU/memory caps, use OS-level controls (cgroups on Linux, Job Objects on Windows, or Docker resource limits).
- **Secrets**: Never injected automatically. Pass secrets explicitly via tool arguments or environment variables, and prefer scoped env vars for subprocess tools to minimize exposure.

#### OS-Level Hardening

For production deployments, add these hardening measures:

| Concern | Docker/Container Solution | Direct Example |
|---------|--------------------------|----------------|
| **CPU/RAM caps** | `--cpus`, `--memory` flags | `docker run --cpus="1.5" --memory="512m" myapp` |
| **Network egress** | Deny-by-default with firewall rules | `--network=none` or custom network with egress filtering |
| **Filesystem** | Read-only root + writable scratch | `--read-only --tmpfs /tmp:rw,size=100m` |

**Example: Run processor in locked-down container**

```bash
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt --no-cache-dir
COPY . .
USER nobody  # Run as non-root
CMD ["python", "app.py"]

# Run with resource limits and network restrictions
docker run \
  --cpus="2" \
  --memory="1g" \
  --memory-swap="1g" \
  --read-only \
  --tmpfs /tmp:rw,size=200m,mode=1777 \
  --network=custom-net \
  --cap-drop=ALL \
  myapp:latest
```

**Network egress controls (deny-by-default)**

```bash
# Create restricted network with no internet access (for local-only tools)
docker network create --internal restricted-net

# Or use iptables for per-tool CIDR allowlists
iptables -A OUTPUT -d 10.0.0.0/8 -j ACCEPT   # Allow private ranges
iptables -A OUTPUT -d 172.16.0.0/12 -j ACCEPT
iptables -A OUTPUT -d 192.168.0.0/16 -j ACCEPT
iptables -A OUTPUT -j DROP  # Deny everything else
```

Example security-focused setup for untrusted code:

```python
import asyncio
from chuk_tool_processor import ToolProcessor, IsolatedStrategy, get_default_registry

async def create_secure_processor():
    # Maximum isolation for untrusted code
    # Runs each tool in a separate process
    registry = await get_default_registry()

    processor = ToolProcessor(
        strategy=IsolatedStrategy(
            registry=registry,
            max_workers=4,
            default_timeout=10.0
        ),
        default_timeout=10.0,
        enable_rate_limiting=True,
        global_rate_limit=50,  # 50 requests/minute
        max_retries=2
    )
    return processor

# For even stricter isolation:
# - Run the entire processor inside a Docker container with resource limits
# - Use network policies to restrict outbound connections
# - Use read-only filesystems where possible
```

## Design Goals & Non-Goals

**What CHUK Tool Processor does:**
- ✅ Parse tool calls from any LLM format (XML, OpenAI, JSON)
- ✅ Execute tools with production policies (timeouts, retries, rate limits, caching)
- ✅ Isolate untrusted code in subprocesses
- ✅ Connect to remote tool servers via MCP (HTTP/STDIO/SSE)
- ✅ Provide composable execution layers (strategies + wrappers)
- ✅ Export tool schemas for LLM prompting

**What CHUK Tool Processor explicitly does NOT do:**
- ❌ Manage conversations or chat history
- ❌ Provide prompt engineering or prompt templates
- ❌ Bundle an LLM client (bring your own OpenAI/Anthropic/local)
- ❌ Implement agent frameworks or chains
- ❌ Make decisions about which tools to call

**Why this matters:** CHUK Tool Processor stays focused on reliable tool execution. It's a building block, not a framework. This makes it composable with any LLM application architecture.

## Architecture Principles

1. **Composability**: Stack strategies and wrappers like middleware
2. **Async-First**: Built for `async/await` from the ground up
3. **Production-Ready**: Timeouts, retries, caching, rate limiting—all built-in
4. **Pluggable**: Parsers, strategies, transports—swap components as needed
5. **Observable**: Structured logging and metrics collection throughout

## Examples

Check out the [`examples/`](examples/) directory for complete working examples:

### Getting Started
- **60-second hello**: `examples/01_getting_started/hello_tool.py` - Absolute minimal example (copy-paste-run)
- **Quick start**: `examples/01_getting_started/quickstart_demo.py` - Basic tool registration and execution
- **Execution strategies**: `examples/01_getting_started/execution_strategies_demo.py` - InProcess vs Subprocess
- **Production wrappers**: `examples/02_production_features/wrappers_demo.py` - Caching, retries, rate limiting
- **Streaming tools**: `examples/03_streaming/streaming_demo.py` - Real-time incremental results
- **Streaming tool calls**: `examples/03_streaming/streaming_tool_calls_demo.py` - Handle partial tool calls from streaming LLMs
- **Schema helper**: `examples/05_schema_and_types/schema_helper_demo.py` - Auto-generate schemas from typed tools (Pydantic → OpenAI/Anthropic/MCP)
- **Observability**: `examples/02_production_features/observability_demo.py` - OpenTelemetry + Prometheus integration

### MCP Integration (Real-World)
- **Notion + OAuth**: `examples/04_mcp_integration/notion_oauth.py` - Complete OAuth 2.1 flow with HTTP Streamable
  - Shows: Authorization Server discovery, client registration, PKCE flow, token exchange
- **SQLite Local**: `examples/04_mcp_integration/stdio_sqlite.py` - Local database access via STDIO
  - Shows: Command/args passing, environment variables, file paths, initialization timeouts
- **Echo Server**: `examples/04_mcp_integration/stdio_echo.py` - Minimal STDIO transport example
  - Shows: Simplest possible MCP integration for testing
- **Atlassian + OAuth**: `examples/04_mcp_integration/atlassian_sse.py` - OAuth with SSE transport (legacy)

### Advanced MCP
- **Plugin system**: `examples/06_plugins/plugins_builtins_demo.py`, `examples/06_plugins/plugins_custom_parser_demo.py`

## FAQ

**Q: What happens if a tool takes too long?**
A: The tool is cancelled after `default_timeout` seconds and returns an error result. The processor continues with other tools.

**Q: Can I mix local and remote (MCP) tools?**
A: Yes! Register local tools first, then use `setup_mcp_*` to add remote tools. They all work in the same processor.

**Q: How do I handle malformed LLM outputs?**
A: The processor is resilient—invalid tool calls are logged and return error results without crashing.

**Q: What about API rate limits?**
A: Use `enable_rate_limiting=True` and set `tool_rate_limits` per tool or `global_rate_limit` for all tools.

**Q: Can tools return files or binary data?**
A: Yes—tools can return any JSON-serializable data including base64-encoded files, URLs, or structured data.

**Q: How do I test my tools?**
A: Use pytest with `@pytest.mark.asyncio`. See [Testing Tools](#testing-tools) for examples.

**Q: Does this work with streaming LLM responses?**
A: Yes—as tool calls appear in the stream, extract and process them. The processor handles partial/incremental tool call lists.

**Q: What's the difference between InProcess and Isolated strategies?**
A: InProcess is faster (same process), Isolated is safer (separate subprocess). Use InProcess for trusted code, Isolated for untrusted.

## Comparison with Other Tools

| Feature | chuk-tool-processor | LangChain Tools | OpenAI Tools | MCP SDK |
|---------|-------------------|-----------------|--------------|---------|
| **Async-native** | ✅ | ⚠️ Partial | ✅ | ✅ |
| **Process isolation** | ✅ IsolatedStrategy | ❌ | ❌ | ⚠️ |
| **Built-in retries** | ✅ | ❌ † | ❌ | ❌ |
| **Rate limiting** | ✅ | ❌ † | ⚠️ ‡ | ❌ |
| **Caching** | ✅ | ⚠️ † | ❌ ‡ | ❌ |
| **Idempotency & de-dup** | ✅ SHA256 keys | ❌ | ❌ | ❌ |
| **Per-tool policies** | ✅ (timeouts/retries/limits) | ⚠️ | ❌ | ❌ |
| **Multiple parsers** | ✅ (XML, OpenAI, JSON) | ⚠️ | ✅ | ✅ |
| **Streaming tools** | ✅ | ⚠️ | ⚠️ | ✅ |
| **MCP integration** | ✅ All transports | ❌ | ❌ | ✅ (protocol only) |
| **Zero-config start** | ✅ | ❌ | ✅ | ⚠️ |
| **Production-ready** | ✅ Timeouts, metrics | ⚠️ | ⚠️ | ⚠️ |

**Notes:**
- † LangChain offers caching and rate-limiting through separate libraries (`langchain-cache`, external rate limiters), but they're not core features.
- ‡ OpenAI Tools can be combined with external rate limiters and caches, but tool execution itself doesn't include these features.

**When to use chuk-tool-processor:**
- You need production-ready tool execution (timeouts, retries, caching)
- You want to connect to MCP servers (local or remote)
- You need to run untrusted code safely (subprocess isolation)
- You're building a custom LLM application (not using a framework)

**When to use alternatives:**
- **LangChain**: You want a full-featured LLM framework with chains, agents, and memory
- **OpenAI Tools**: You only use OpenAI and don't need advanced execution features
- **MCP SDK**: You're building an MCP server, not a client

## Related Projects

- **[chuk-mcp](https://github.com/chrishayuk/chuk-mcp)**: Low-level Model Context Protocol client
  - Powers the MCP transport layer in chuk-tool-processor
  - Use directly if you need protocol-level control
  - Use chuk-tool-processor if you want high-level tool execution

## Development & Publishing

### For Contributors

Development setup:

```bash
# Clone repository
git clone https://github.com/chrishayuk/chuk-tool-processor.git
cd chuk-tool-processor

# Install development dependencies
uv sync --dev

# Run tests
make test

# Run all quality checks
make check
```

### For Maintainers: Publishing Releases

The project uses **fully automated CI/CD** for releases. Publishing is as simple as:

```bash
# 1. Bump version
make bump-patch    # or bump-minor, bump-major

# 2. Commit version change
git add pyproject.toml
git commit -m "version X.Y.Z"
git push

# 3. Create release (automated)
make publish
```

This will:
- Create and push a git tag
- Trigger GitHub Actions to create a release with auto-generated changelog
- Run tests across all platforms and Python versions
- Build and publish to PyPI automatically

For detailed release documentation, see:
- **[RELEASING.md](RELEASING.md)** - Complete release process guide
- **[docs/CI-CD.md](docs/CI-CD.md)** - Full CI/CD pipeline documentation

## Stability & Versioning

CHUK Tool Processor follows **[Semantic Versioning 2.0.0](https://semver.org/)** for predictable upgrades:

* **Breaking changes** = **major** version bump (e.g., 1.x → 2.0)
* **New features** (backward-compatible) = **minor** version bump (e.g., 1.2 → 1.3)
* **Bug fixes** (backward-compatible) = **patch** version bump (e.g., 1.2.3 → 1.2.4)

**Public API surface**: Everything exported via the package root (`from chuk_tool_processor import ...`) is considered public API and follows semver guarantees.

**Deprecation policy**: Deprecated APIs will:
1. Log a warning for **one minor release**
2. Be removed in the **next major release**

**Upgrading safely**:
* Patch and minor updates are **safe to deploy** without code changes
* Major updates may require migration—see release notes
* Pin to `chuk-tool-processor~=1.2` for minor updates only, or `chuk-tool-processor==1.2.3` for exact versions

## Contributing & Support

- **GitHub**: [chrishayuk/chuk-tool-processor](https://github.com/chrishayuk/chuk-tool-processor)
- **Issues**: [Report bugs and request features](https://github.com/chrishayuk/chuk-tool-processor/issues)
- **Discussions**: [Community discussions](https://github.com/chrishayuk/chuk-tool-processor/discussions)
- **License**: MIT

---

**Remember**: CHUK Tool Processor is the missing link between LLM outputs and reliable tool execution. It's not trying to be everything—it's trying to be the best at one thing: processing tool calls in production.

Built with ❤️ by the CHUK AI team for the LLM tool integration community.