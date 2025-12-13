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

Works with OpenAI, Anthropic, local models (Ollama/MLX/vLLM), and any framework (LangChain, LlamaIndex, custom).

---

## Architecture

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
│   • Bulkhead                │
└─────────────────────────────┘
        ↓
   Execution Strategy
   ┌──────────────────────┐
   │ • InProcess          │  ← Fast, trusted
   │ • Isolated/Subprocess│  ← Safe, untrusted
   │ • Remote via MCP     │  ← Distributed
   └──────────────────────┘
```

---

## Quick Start

### Installation

```bash
pip install chuk-tool-processor

# Or with uv (recommended)
uv pip install chuk-tool-processor
```

### 60-Second Example

```python
import asyncio
from chuk_tool_processor import ToolProcessor, tool

@tool(name="calculator")
class Calculator:
    async def execute(self, operation: str, a: float, b: float) -> dict:
        ops = {"add": a + b, "multiply": a * b, "subtract": a - b}
        return {"result": ops.get(operation, 0)}

async def main():
    async with ToolProcessor(enable_caching=True, enable_retries=True) as p:
        # Works with OpenAI, Anthropic, or JSON formats
        result = await p.process('<tool name="calculator" args=\'{"operation": "multiply", "a": 15, "b": 23}\'/>')
        print(result[0].result)  # {'result': 345}

asyncio.run(main())
```

**That's it.** You now have production-ready tool execution with timeouts, retries, and caching.

### Works with Any LLM Format

```python
# Anthropic XML format
anthropic_output = '<tool name="search" args=\'{"query": "Python"}\'/>'

# OpenAI tool_calls format
openai_output = {
    "tool_calls": [{
        "type": "function",
        "function": {"name": "search", "arguments": '{"query": "Python"}'}
    }]
}

# Direct JSON
json_output = [{"tool": "search", "arguments": {"query": "Python"}}]

# All work identically
results = await processor.process(anthropic_output)
results = await processor.process(openai_output)
results = await processor.process(json_output)
```

---

## Key Features

### Production Reliability

| Feature | Description |
|---------|-------------|
| **Timeouts** | Every tool execution has proper timeout handling |
| **Retries** | Automatic retry with exponential backoff and jitter |
| **Rate Limiting** | Global and per-tool rate limits with sliding windows |
| **Caching** | Result caching with TTL and SHA256-based idempotency keys |
| **Circuit Breakers** | Prevent cascading failures with automatic recovery |

### Multi-Tenant & Isolation

| Feature | Description |
|---------|-------------|
| **Bulkheads** | Per-tool/namespace concurrency limits to prevent resource starvation |
| **Scoped Registries** | Isolated registries for multi-tenant apps and testing |
| **ExecutionContext** | Request-scoped metadata propagation (user, tenant, tracing, deadlines) |
| **Isolated Strategy** | Subprocess execution for untrusted code (zero crash blast radius) |

### Integration & Observability

| Feature | Description |
|---------|-------------|
| **Multi-Format Parsing** | XML (Anthropic), OpenAI `tool_calls`, JSON — all work automatically |
| **MCP Integration** | Connect to remote tools via HTTP Streamable, STDIO, SSE |
| **OpenTelemetry** | Distributed tracing with automatic span creation |
| **Prometheus** | Metrics for error rates, latency, cache hits, circuit breaker state |
| **Type Safety** | PEP 561 compliant with full mypy support |

---

## Production Configuration

```python
async with ToolProcessor(
    # Execution settings
    default_timeout=30.0,
    max_concurrency=20,

    # Reliability features
    enable_caching=True,
    cache_ttl=600,
    enable_rate_limiting=True,
    global_rate_limit=100,
    tool_rate_limits={"expensive_api": (5, 60)},  # 5 req/min
    enable_retries=True,
    max_retries=3,
    enable_circuit_breaker=True,
    circuit_breaker_threshold=5,

    # Multi-tenant isolation
    enable_bulkhead=True,
    bulkhead_config=BulkheadConfig(
        default_limit=10,
        tool_limits={"slow_api": 2},
    ),
) as processor:
    # Execute with request context
    ctx = ExecutionContext(
        request_id="req-123",
        user_id="user-456",
        tenant_id="acme-corp",
    )
    results = await processor.process(llm_output, context=ctx)
```

---

## MCP Integration

Connect to remote tool servers using the [Model Context Protocol](https://modelcontextprotocol.io):

```python
from chuk_tool_processor.mcp import setup_mcp_http_streamable

# Cloud services (Notion, etc.)
processor, manager = await setup_mcp_http_streamable(
    servers=[{
        "name": "notion",
        "url": "https://mcp.notion.com/mcp",
        "headers": {"Authorization": f"Bearer {token}"}
    }],
    namespace="notion",
    enable_caching=True,
    enable_retries=True
)

# Use remote tools
results = await processor.process(
    '<tool name="notion.search_pages" args=\'{"query": "docs"}\'/>'
)
```

**Transport Options:**

| Transport | Use Case | Example |
|-----------|----------|---------|
| **HTTP Streamable** | Cloud SaaS with OAuth | Notion, custom APIs |
| **STDIO** | Local tools, databases | SQLite, file systems |
| **SSE** | Legacy MCP servers | Atlassian |

See [MCP_INTEGRATION.md](docs/MCP_INTEGRATION.md) for complete examples with OAuth token refresh.

---

## Observability

One-line setup for production monitoring:

```python
from chuk_tool_processor.observability import setup_observability

setup_observability(
    service_name="my-tool-service",
    enable_tracing=True,     # → OpenTelemetry traces
    enable_metrics=True,     # → Prometheus metrics at :9090/metrics
    metrics_port=9090
)
# Every tool execution is now automatically traced and metered
```

**What you get:**
- Distributed traces (Jaeger, Zipkin, any OTLP collector)
- Prometheus metrics (error rate, latency P50/P95/P99, cache hit rate)
- Circuit breaker state monitoring
- Zero code changes to your tools

See [OBSERVABILITY.md](docs/OBSERVABILITY.md) for complete setup guide.

---

## Documentation

| Document | Description |
|----------|-------------|
| [**GETTING_STARTED.md**](docs/GETTING_STARTED.md) | Creating tools, using the processor, ValidatedTool, StreamingTool |
| [**CORE_CONCEPTS.md**](docs/CORE_CONCEPTS.md) | Registry, strategies, wrappers, parsers, MCP overview |
| [**PRODUCTION_PATTERNS.md**](docs/PRODUCTION_PATTERNS.md) | Bulkheads, scoped registries, ExecutionContext, parallel execution |
| [**MCP_INTEGRATION.md**](docs/MCP_INTEGRATION.md) | HTTP Streamable, STDIO, SSE, OAuth token refresh |
| [**ADVANCED_TOPICS.md**](docs/ADVANCED_TOPICS.md) | Deferred loading, code sandbox, isolated strategy, testing |
| [**CONFIGURATION.md**](docs/CONFIGURATION.md) | All config options and environment variables |
| [**OBSERVABILITY.md**](docs/OBSERVABILITY.md) | OpenTelemetry, Prometheus, metrics reference |
| [**ERRORS.md**](docs/ERRORS.md) | Error codes and handling patterns |

---

## Examples

```bash
# Getting started
python examples/01_getting_started/hello_tool.py

# Production patterns (bulkheads, context, scoped registries)
python examples/02_production_features/production_patterns_demo.py

# Observability demo
python examples/02_production_features/observability_demo.py

# MCP integration
python examples/04_mcp_integration/stdio_echo.py
python examples/04_mcp_integration/notion_oauth.py
```

See [examples/](examples/) for 20+ working examples.

---

## Compatibility

| Component | Supported |
|-----------|-----------|
| **Python** | 3.11, 3.12, 3.13 |
| **Platforms** | macOS, Linux, Windows |
| **LLM Providers** | OpenAI, Anthropic, Local models (Ollama, MLX, vLLM) |
| **MCP Transports** | HTTP Streamable, STDIO, SSE |
| **MCP Spec** | 2025-11-25, 2025-06-18, 2025-03-26 |

---

## Installation Options

```bash
# Core package
pip install chuk-tool-processor

# With observability (OpenTelemetry + Prometheus)
pip install chuk-tool-processor[observability]

# With MCP support
pip install chuk-tool-processor[mcp]

# With fast JSON (2-3x faster with orjson)
pip install chuk-tool-processor[fast-json]

# All extras
pip install chuk-tool-processor[all]
```

---

## When to Use This

**Use CHUK Tool Processor when:**
- Your LLM calls tools or APIs
- You need retries, timeouts, caching, or rate limits
- You need to run untrusted tools safely
- Your tools are local or remote (MCP)
- You need multi-tenant isolation
- You want production-grade observability

**Don't use this if:**
- You want an agent framework (this is the execution layer, not the agent)
- You want conversation flow/memory orchestration

> **Not a framework.** If LangChain/LlamaIndex help decide *which* tool to call, CHUK Tool Processor makes sure the tool call **actually succeeds**.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

```bash
# Development setup
git clone https://github.com/chrishayuk/chuk-tool-processor.git
cd chuk-tool-processor
uv pip install -e ".[dev]"

# Run tests
make check
```

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Related Projects

- [chuk-mcp](https://github.com/chrishayuk/chuk-mcp) - Low-level MCP protocol client
- [Model Context Protocol](https://modelcontextprotocol.io) - MCP specification
