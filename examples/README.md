# CHUK Tool Processor - Examples

Complete, runnable examples for all features. **Start with `01_getting_started/`.**

---

## 📚 Learning Path

### 01 → Getting Started (Start Here!)

**New to CHUK Tool Processor? Start here:**

| Example | Description | Time |
|---------|-------------|------|
| **[hello_tool.py](01_getting_started/hello_tool.py)** | 60-second intro - Parse XML, OpenAI, JSON formats | 1 min |
| **[quickstart_demo.py](01_getting_started/quickstart_demo.py)** | Full quick start - Registration, execution, errors | 3 min |
| **[execution_strategies_demo.py](01_getting_started/execution_strategies_demo.py)** | InProcess vs Isolated (subprocess) strategies | 5 min |

**Run any example:**
```bash
uv run python examples/01_getting_started/hello_tool.py
```

---

### 02 → Production Features

**Add timeouts, retries, caching, and observability:**

| Example | Description |
|---------|-------------|
| **[wrappers_demo.py](02_production_features/wrappers_demo.py)** | Caching, retries, rate limits, circuit breakers |
| **[observability_demo.py](02_production_features/observability_demo.py)** | OpenTelemetry + Prometheus integration |
| **[guards_demo.py](../guards_demo.py)** | Runtime guards: validation, security, resource limits |

---

### 03 → Streaming

**Real-time tool execution and incremental results:**

| Example | Description |
|---------|-------------|
| **[streaming_demo.py](03_streaming/streaming_demo.py)** | StreamingTool pattern for incremental results |
| **[streaming_tool_calls_demo.py](03_streaming/streaming_tool_calls_demo.py)** | Handle partial tool calls from streaming LLMs |

---

### 04 → MCP Integration (Remote Tools)

**Connect to external tools via Model Context Protocol:**

| Example | Description | Transport |
|---------|-------------|-----------|
| **[notion_oauth.py](04_mcp_integration/notion_oauth.py)** | Complete OAuth 2.1 flow with Notion | HTTP Streamable |
| **[stdio_sqlite.py](04_mcp_integration/stdio_sqlite.py)** | Local database access via MCP | STDIO |
| **[stdio_echo.py](04_mcp_integration/stdio_echo.py)** | Simple echo server (testing) | STDIO |
| **[mcp_http_streamable_example.py](04_mcp_integration/mcp_http_streamable_example.py)** | HTTP Streamable transport demo | HTTP |
| **[atlassian_sse.py](04_mcp_integration/atlassian_sse.py)** | Atlassian with OAuth | SSE |

**MCP Quick Start:**
```python
from chuk_tool_processor import setup_mcp_http_streamable

# Connect to Notion
processor, manager = await setup_mcp_http_streamable(
    servers=[{"name": "notion", "url": "https://mcp.notion.com/mcp",
              "headers": {"Authorization": f"Bearer {token}"}}],
    namespace="notion"
)

# Use Notion tools
results = await processor.process('<tool name="notion.search_pages" args=\'{"query": "docs"}\'/>')
```

---

### 05 → Schema & Type Safety

**Auto-generate schemas for LLMs:**

| Example | Description |
|---------|-------------|
| **[schema_helper_demo.py](05_schema_and_types/schema_helper_demo.py)** | Export tool schemas to OpenAI/Anthropic/MCP formats |

---

### 06 → Plugins

**Extend parsing and tool discovery:**

| Example | Description |
|---------|-------------|
| **[plugins_builtins_demo.py](06_plugins/plugins_builtins_demo.py)** | Built-in parsers (XML, OpenAI, JSON) |
| **[plugins_custom_parser_demo.py](06_plugins/plugins_custom_parser_demo.py)** | Write custom parsers |

---

### 07 → Dynamic Tool Discovery

**Let LLMs discover and execute tools on-demand:**

| Example | Description |
|---------|-------------|
| **[dynamic_tools_demo.py](07_discovery/dynamic_tools_demo.py)** | Intelligent search, synonym expansion, fuzzy matching, session boosting |

The discovery module bridges the gap between how LLMs describe tools and how tools are named in code:

```python
from chuk_tool_processor.discovery import ToolSearchEngine, BaseDynamicToolProvider

# Search finds tools using natural language
engine = ToolSearchEngine()
engine.set_tools(my_tools)

# "gaussian" finds "normal_cdf", "average" finds "calculate_mean"
results = engine.search("gaussian distribution cdf")

# Dynamic provider gives LLMs 4 meta-tools:
# list_tools, search_tools, get_tool_schema, call_tool
class MyProvider(BaseDynamicToolProvider):
    async def get_all_tools(self): ...
    async def execute_tool(self, name, args): ...
```

**Key features:**
- **Synonym expansion**: "gaussian" → "normal", "cdf" → "cumulative"
- **Fuzzy matching**: "multipley" finds "multiply" (typo tolerance)
- **Session boosting**: Recently used tools rank higher
- **Alias resolution**: "normalCdf" and "normal_cdf" both work

---

## 🚀 Advanced Examples

**For specialized integrations and advanced patterns:**

Located in **[advanced/](advanced/)**:

| Example | Description |
|---------|-------------|
| `context7_integration.py` | Context7 integration |
| `fastapi_registry.py` | FastAPI + tool registry |
| `langchain_integration.py` | LangChain tools |
| `bearer_token_auth.py` | Bearer token authentication |
| `oauth_error_handling.py` | OAuth error handling |
| `transport_error_handling.py` | Transport error handling |
| `gateway_integration.py` | Gateway integration |
| `resilience_*_demo.py` | Resilience patterns (4 variants) |

---

## 🛠️ Test Servers

**MCP test servers for local development:**

Located in **[servers/](servers/)**:

| Server | Description |
|--------|-------------|
| `mcp_sse_server.py` | SSE test server |
| `mcp_http_server.py` | HTTP Streamable test server |
| `reliable_test_sse_server.py` | Reliable SSE server |

---

## 🎯 Quick Reference

### Common Patterns

**Basic Tool Registration:**
```python
from chuk_tool_processor import ToolProcessor, register_tool, initialize

@register_tool(name="my_tool")
class MyTool:
    async def execute(self, arg: str) -> dict:
        return {"result": f"Processed: {arg}"}

await initialize()
async with ToolProcessor() as processor:
    results = await processor.process('<tool name="my_tool" args=\'{"arg": "hello"}\'/>')
```

**With Production Features:**
```python
async with ToolProcessor(
    enable_caching=True,
    enable_retries=True,
    max_retries=3,
    enable_rate_limiting=True,
    global_rate_limit=100,  # 100 requests/min
) as processor:
    results = await processor.process(llm_output)
```

**Isolated Execution (Subprocess):**
```python
from chuk_tool_processor import IsolatedStrategy, get_default_registry

registry = await get_default_registry()
async with ToolProcessor(
    strategy=IsolatedStrategy(registry=registry, max_workers=4)
) as processor:
    results = await processor.process(llm_output)
```

---

## 📖 Documentation

For complete documentation, see:
- **[../README.md](../README.md)** - Main documentation
- **[../docs/CONFIGURATION.md](../docs/CONFIGURATION.md)** - All configuration options
- **[../docs/DISCOVERY.md](../docs/DISCOVERY.md)** - Dynamic tool discovery & search
- **[../docs/GUARDS.md](../docs/GUARDS.md)** - Runtime guards for safety & validation
- **[../docs/OBSERVABILITY.md](../docs/OBSERVABILITY.md)** - Metrics & tracing
- **[../docs/ERRORS.md](../docs/ERRORS.md)** - Error codes & handling
- **[../docs/MCP.md](../docs/MCP.md)** - MCP integration guide

---

## 🤝 Contributing Examples

Have a useful example? Please contribute!

**Good examples are:**
- ✅ Focused on one concept
- ✅ Copy-paste runnable
- ✅ Well-commented
- ✅ Follow DX patterns (clean imports, context managers)

See [CONTRIBUTING.md](../CONTRIBUTING.md) for details.
