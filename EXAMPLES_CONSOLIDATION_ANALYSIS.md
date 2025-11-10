# Examples Directory Consolidation Analysis

## Current State
- **52 total example files**
- **~17 referenced in README**
- **35 unreferenced examples** (potential candidates for consolidation/removal)

## Problems
1. **Too many files** - Overwhelming for new users
2. **Duplicate patterns** - Multiple files showing the same concept
3. **Test files mixed in** - Debug/diagnostic scripts in examples/
4. **No clear organization** - Hard to find the right example

---

## Recommended Consolidation Strategy

### ✅ Keep (Core Examples - Referenced in README)

**Getting Started (4 files):**
- `hello_tool.py` - 60-second intro
- `quickstart_demo.py` - Full quick start
- `execution_strategies_demo.py` - InProcess vs Isolated
- `wrappers_demo.py` - Caching, retries, rate limits

**Streaming (2 files):**
- `streaming_demo.py` - StreamingTool pattern
- `streaming_tool_calls_demo.py` - Handle partial tool calls

**Schema & Type Safety (1 file):**
- `schema_helper_demo.py` - Generate schemas for LLMs

**Observability (1 file):**
- `observability_demo.py` - OpenTelemetry + Prometheus

**MCP Integration (5 files):**
- `notion_oauth.py` - Real OAuth flow
- `stdio_sqlite.py` - Local database via STDIO
- `stdio_echo.py` - Simple STDIO example
- `mcp_http_streamable_example.py` - HTTP Streamable transport
- `atlassian_sse.py` - SSE transport with OAuth

**Plugins (2 files):**
- `plugins_builtins_demo.py` - Built-in parsers
- `plugins_custom_parser_demo.py` - Custom parser

**Total: 15 core examples**

---

### ❌ Remove or Consolidate

#### 1. Duplicate MCP Examples (Consolidate → 1-2 files)

**Duplicates showing same pattern:**
- `mcp_sse_example.py` (7K) - Basic SSE
- `mcp_sse_example_calling_usage.py` (11K) - SSE with calling
- `async_sse_mcp_client.py` (14K) - Another SSE variant
- `remote_sse_calling_example.py` (19K) - Yet another SSE
- `mcp_sse_example_subprocess_strategy.py` (11K) - SSE with subprocess

**Recommendation:** Keep `atlassian_sse.py` (shows OAuth). Delete others OR consolidate to one `mcp_sse_complete_demo.py`

**HTTP Streamable duplicates:**
- `mcp_http_streamable_example.py` (9K) ← Keep (in README)
- `mcp_http_streamable_example_calling_usage.py` (10K)
- `mcp_streamable_http_example_calling_usage.py` (12K) ← Duplicate name!

**Recommendation:** Keep one, delete rest

**STDIO duplicates:**
- `mcp_stdio_example.py` (6K)
- `mcp_stdio_example_calling_usage.py` (10K)
- `mcp_stdio_example_subprocess_strategy.py` (12K)
- `mcp_stdio_example_resources.py` (6K)
- `stdio_sqlite.py` (8K) ← Keep (in README)
- `stdio_echo.py` (4K) ← Keep (in README)

**Recommendation:** Keep sqlite + echo, delete others

#### 2. Test/Debug Files (Move to tests/ or delete)

- `mcp_timeout_bug_demo.py` (6K) - Bug demo
- `timeout_bug_demo.py` (8K) - Bug demo
- `simple_test_mcp.py` (10K) - Test file
- `generate_metrics.py` (5K) - Metrics generator
- `run_sse_demo.py` (3K) - Runner script
- `run_streamable_http_demo.py` (14K) - Runner script

**Recommendation:** Move to `tests/manual/` or `scripts/`

#### 3. Diagnostic Files (Move to tools/ or delete)

- `health_diagnostic.py` (26K)
- `gateway_health_diagnostic.py` (30K)
- `sse_diagnostic.py` (27K)

**Recommendation:** Move to `tools/diagnostics/` or delete if unused

#### 4. Server Files (Move to examples/servers/)

- `mcp_sse_server.py` (15K)
- `mcp_streamable_http_server.py` (16K)
- `reliable_test_sse_server.py` (12K)

**Recommendation:** Create `examples/servers/` directory

#### 5. Resilience Demos (Consolidate → 1 file)

- `resilience_http_streamable_demo.py` (37K)
- `resilience_sse_demo.py` (32K)
- `resilience_stdio_demo.py` (34K)
- `resilience_substrategy_demo.py` (45K)

**Total: 148K (!)** showing nearly identical patterns

**Recommendation:** Consolidate to single `resilience_patterns_demo.py` (15-20K) showing all transports

#### 6. Specialized Demos (Move to examples/advanced/)

- `context7_chuk_integration_demo.py` (18K) - Context7 integration
- `demo_bearer_token.py` (13K) - Bearer token
- `demo_langchain_tool.py` (3K) - LangChain
- `fastapi_registry_example.py` (11K) - FastAPI
- `gateway_integration_demo.py` (24K) - Gateway
- `oauth_error_handling.py` (15K) - OAuth errors
- `transport_error_handling.py` (13K) - Transport errors

**Recommendation:** Create `examples/advanced/` directory

#### 7. Unused/Unclear Examples

- `execution_strategies_custom_demo.py` (2K) - Seems redundant with main strategies demo
- `plugins_discovery_demo.py` (3K) - Unclear if needed
- `registry_example.py` (7K) - Covered in quickstart

---

## Proposed New Structure

```
examples/
├── README.md                          # Index of all examples
│
├── 01_getting_started/
│   ├── hello_tool.py                  # 60-second intro
│   ├── quickstart_demo.py             # Full quick start
│   └── execution_strategies_demo.py   # InProcess vs Isolated
│
├── 02_production_features/
│   ├── wrappers_demo.py               # Caching, retries, rate limits
│   ├── observability_demo.py          # OpenTelemetry + Prometheus
│   └── resilience_patterns_demo.py    # NEW: Consolidated resilience
│
├── 03_streaming/
│   ├── streaming_demo.py              # StreamingTool pattern
│   └── streaming_tool_calls_demo.py   # Partial tool calls
│
├── 04_mcp_integration/
│   ├── notion_oauth.py                # OAuth flow
│   ├── stdio_sqlite.py                # Local database
│   ├── stdio_echo.py                  # Simple STDIO
│   ├── mcp_http_streamable_example.py # HTTP transport
│   └── atlassian_sse.py               # SSE transport
│
├── 05_schema_and_types/
│   └── schema_helper_demo.py          # Schema generation
│
├── 06_plugins/
│   ├── plugins_builtins_demo.py       # Built-in parsers
│   └── plugins_custom_parser_demo.py  # Custom parser
│
├── advanced/                          # Moved from root
│   ├── context7_integration.py
│   ├── fastapi_registry.py
│   ├── langchain_integration.py
│   ├── bearer_token_auth.py
│   └── ...
│
└── servers/                           # Test servers
    ├── mcp_sse_server.py
    └── mcp_http_server.py
```

---

## Consolidation Summary

| Action | Count | Files |
|--------|-------|-------|
| **Keep as-is** | 15 | Core examples referenced in README |
| **Delete** | 15+ | Duplicates, test files |
| **Consolidate** | 4 → 1 | Resilience demos |
| **Move to advanced/** | 7 | Specialized integrations |
| **Move to servers/** | 3 | Test servers |
| **Move to tools/** | 3 | Diagnostic scripts |

**Result: 52 → ~25 examples** (15 core + 10 advanced)

---

## Migration Steps

1. Create new directory structure
2. Move core 15 examples to numbered folders
3. Consolidate 4 resilience demos → 1 file
4. Move specialized examples to advanced/
5. Move servers to servers/
6. Delete duplicates
7. Update README with new structure
8. Add examples/README.md as index

---

## Benefits

✅ **Clearer learning path** - Numbered folders guide users
✅ **Reduced cognitive load** - 15 core examples vs 52
✅ **Better discoverability** - Organized by topic
✅ **Less maintenance** - Fewer files to keep updated
✅ **Production focus** - Core examples show best practices
