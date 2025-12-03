# MCP Deferred Loading

> Scale MCP servers to unlimited tools with dynamic loading

## Overview

MCP servers can expose hundreds or thousands of tools. With **deferred loading**, you can register MCP servers with 500+ tools while only loading a handful initially, breaking through the 128 function limit.

## The Problem

```python
# MCP server exposes 200 tools
mcp_tools = stream_manager.get_all_tools()  # Returns 200 tools

# Register all tools
await register_mcp_tools(stream_manager, namespace="mcp")

# ❌ ERROR: 200 tools > 128 limit!
response = client.messages.create(
    model="claude-3-5-sonnet",
    tools=get_all_tool_schemas()  # Too many!
)
```

## The Solution

```python
from chuk_tool_processor.mcp.register_mcp_tools import register_mcp_tools

# Register with deferred loading
await register_mcp_tools(
    stream_manager=stream_manager,
    namespace="filesystem",
    defer_loading=True,  # Defer all tools by default
    defer_all_except=["ls", "cd", "pwd"],  # Keep these core tools loaded
)

# Result:
# ✅ 3 tools active (ls, cd, pwd)
# ✅ 197 tools deferred (loaded on-demand)
```

## API Reference

### register_mcp_tools Parameters

```python
await register_mcp_tools(
    stream_manager: StreamManager,
    namespace: str = "mcp",
    # Resilience configuration
    default_timeout: float = 30.0,
    enable_resilience: bool = True,
    recovery_config: RecoveryConfig | None = None,
    # Deferred loading configuration
    defer_loading: bool = False,
    defer_all_except: list[str] | None = None,
    defer_only: list[str] | None = None,
    search_keywords_fn: Callable | None = None,
) -> list[str]
```

#### Deferred Loading Parameters

- **defer_loading**: If `True`, defer all tools by default
- **defer_all_except**: List of tool names to load eagerly (only used if `defer_loading=True`)
- **defer_only**: List of specific tools to defer (only used if `defer_loading=False`)
- **search_keywords_fn**: Optional function `(tool_name, tool_def) -> list[str]` to generate custom search keywords

### Search Keywords Function

By default, search keywords are extracted from tool names and descriptions. You can provide a custom function for better control:

```python
def custom_keywords(tool_name: str, tool_def: dict) -> list[str]:
    """Generate custom search keywords based on tool definition."""
    keywords = [tool_name.lower()]

    # Add category-specific keywords
    if "query" in tool_name:
        keywords.extend(["database", "sql", "select"])
    elif "write" in tool_name:
        keywords.extend(["file", "disk", "save"])

    return keywords

await register_mcp_tools(
    stream_manager=stream_manager,
    namespace="mcp",
    defer_loading=True,
    defer_all_except=["core_tool"],
    search_keywords_fn=custom_keywords,
)
```

## Usage Patterns

### Pattern 1: Defer All Except Core

Best for MCP servers with many specialized tools.

```python
# Filesystem server with 150 tools
await register_mcp_tools(
    stream_manager=fs_stream,
    namespace="filesystem",
    defer_loading=True,
    defer_all_except=[
        "ls",           # List directory
        "cd",           # Change directory
        "pwd",          # Print working directory
    ],
)

# Result:
# ✅ 3 core tools loaded
# ✅ 147 specialized tools deferred
```

### Pattern 2: Defer Specific Tools

Best for MCP servers where most tools are commonly used.

```python
# API server with some heavy tools
await register_mcp_tools(
    stream_manager=api_stream,
    namespace="api",
    defer_loading=False,  # Load all by default
    defer_only=[
        "batch_process_large_dataset",  # Heavy operation
        "export_full_analytics",         # Rarely used
        "generate_comprehensive_report", # Resource intensive
    ],
)

# Result:
# ✅ Most tools loaded (commonly used)
# ✅ 3 heavy tools deferred
```

### Pattern 3: Database Tools

```python
# Database server with 200 tools
await register_mcp_tools(
    stream_manager=db_stream,
    namespace="postgres",
    defer_loading=True,
    defer_all_except=[
        "connect",
        "disconnect",
        "ping",
    ],
)

# User: "Query my users table"
# → tool_search finds "query" tools
# → Loads postgres_query, postgres_select, etc.
# → User can now execute queries
```

### Pattern 4: Cloud Provider

```python
# AWS MCP with 500+ tools
await register_mcp_tools(
    stream_manager=aws_stream,
    namespace="aws",
    defer_loading=True,
    defer_all_except=[
        "auth",
        "list_services",
        "get_account_info",
    ],
)

# User: "List my S3 buckets"
# → tool_search("s3 list buckets")
# → Loads S3 tools
# → User can access S3

# User: "Create an EC2 instance"
# → tool_search("ec2 create instance")
# → Loads EC2 tools
# → User can manage EC2
```

## Architecture

### Pydantic-Native Storage

MCP deferred tool parameters are stored using Pydantic models (no dict goop!):

```python
from chuk_tool_processor.registry.metadata import MCPToolFactoryParams

factory_params = MCPToolFactoryParams(
    tool_name="db_query",
    default_timeout=30.0,
    enable_resilience=True,
    recovery_config=None,
    namespace="postgres",
)

metadata = ToolMetadata(
    name="db_query",
    namespace="postgres",
    defer_loading=True,
    mcp_factory_params=factory_params,  # Typed field!
)
```

### StreamManager Storage

The registry stores StreamManager references by namespace:

```python
# During registration
registry.set_stream_manager("postgres", stream_manager)

# During deferred loading
tool = await registry.load_deferred_tool("query", "postgres")
# → Retrieves stream_manager for "postgres"
# → Creates MCPTool with stream_manager
```

### Lazy Tool Creation

When a deferred MCP tool is loaded:

```python
# 1. Registry checks metadata.mcp_factory_params
# 2. Retrieves StreamManager for the namespace
# 3. Creates MCPTool instance:
tool = MCPTool(
    tool_name=factory_params.tool_name,
    stream_manager=registry.get_stream_manager(namespace),
    default_timeout=factory_params.default_timeout,
    enable_resilience=factory_params.enable_resilience,
    recovery_config=factory_params.recovery_config,
)
```

## Real-World Examples

### Example 1: Filesystem MCP

```python
from chuk_tool_processor.mcp.setup_mcp_stdio import setup_mcp_stdio
from chuk_tool_processor.mcp.register_mcp_tools import register_mcp_tools

# Setup filesystem MCP server
stream_manager = await setup_mcp_stdio(
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/dir"]
)

# Register with deferred loading
await register_mcp_tools(
    stream_manager=stream_manager,
    namespace="fs",
    defer_loading=True,
    defer_all_except=["ls", "cd", "pwd", "cat"],
)

# API Call #1: Start with 4 core tools
# User: "Find all .py files"
# → tool_search("find files python")
# → Loads: find, grep, search tools

# API Call #2: Now have 7 tools
# Claude can now search files
```

### Example 2: Database MCP

```python
# Setup Postgres MCP server
stream_manager = await setup_mcp_stdio(
    command="npx",
    args=["-y", "@modelcontextprotocol/server-postgres",
          "postgresql://localhost/mydb"]
)

# Register with deferred loading
def db_keywords(tool_name: str, tool_def: dict) -> list[str]:
    """Custom keywords for database tools."""
    keywords = [tool_name.lower()]

    if "query" in tool_name or "select" in tool_name:
        keywords.extend(["query", "select", "read", "fetch"])
    elif "insert" in tool_name or "create" in tool_name:
        keywords.extend(["insert", "create", "add", "write"])
    elif "update" in tool_name:
        keywords.extend(["update", "modify", "change"])

    return keywords

await register_mcp_tools(
    stream_manager=stream_manager,
    namespace="postgres",
    defer_loading=True,
    defer_all_except=["connect", "disconnect", "ping"],
    search_keywords_fn=db_keywords,
)
```

### Example 3: Multiple MCP Servers

```python
# Filesystem server
fs_stream = await setup_mcp_stdio(
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/data"]
)

await register_mcp_tools(
    stream_manager=fs_stream,
    namespace="filesystem",
    defer_loading=True,
    defer_all_except=["ls", "pwd"],
)

# Database server
db_stream = await setup_mcp_stdio(
    command="npx",
    args=["-y", "@modelcontextprotocol/server-postgres",
          "postgresql://localhost/mydb"]
)

await register_mcp_tools(
    stream_manager=db_stream,
    namespace="database",
    defer_loading=True,
    defer_all_except=["connect", "ping"],
)

# Result:
# ✅ 4 core tools loaded (2 fs + 2 db)
# ✅ 300+ deferred tools available
# ✅ Well under 128 limit!
```

## Best Practices

### 1. Choose the Right Core Tools

Keep commonly-used tools loaded:

```python
# ✅ Good: Common operations
defer_all_except=["ls", "cd", "pwd", "cat"]

# ❌ Bad: Rarely used operations
defer_all_except=["recursive_deep_analysis", "batch_export"]
```

### 2. Use Descriptive Search Keywords

```python
def good_keywords(tool_name: str, tool_def: dict) -> list[str]:
    """Extract meaningful keywords."""
    keywords = []

    # Include variations
    if "query" in tool_name:
        keywords.extend(["query", "select", "search", "find"])

    # Include domain terms
    if tool_def.get("description"):
        desc = tool_def["description"].lower()
        if "sql" in desc:
            keywords.extend(["sql", "database", "table"])

    return keywords
```

### 3. Namespace by Domain

```python
# ✅ Good: Separate namespaces
await register_mcp_tools(fs_stream, namespace="filesystem")
await register_mcp_tools(db_stream, namespace="database")
await register_mcp_tools(api_stream, namespace="api")

# ❌ Bad: Everything in one namespace
await register_mcp_tools(fs_stream, namespace="mcp")
await register_mcp_tools(db_stream, namespace="mcp")  # Confusing!
```

### 4. Monitor Active Tools

```python
registry = await get_default_registry()

# Check what's loaded
active = await registry.get_active_tools()
deferred = await registry.get_deferred_tools()

logger.info(f"Active: {len(active)}, Deferred: {len(deferred)}")

# Ensure under limit
assert len(active) < 128, "Too many active tools!"
```

## Troubleshooting

### Issue: StreamManager not found when loading deferred tool

**Error:**
```
ValueError: No StreamManager found for namespace 'postgres'.
Call set_stream_manager() before loading deferred MCP tools.
```

**Solution:**
```python
# Ensure register_mcp_tools is called before loading
await register_mcp_tools(stream_manager, namespace="postgres")

# Now you can load deferred tools
await registry.load_deferred_tool("query", "postgres")
```

### Issue: All tools loading eagerly

**Problem:** `defer_loading=True` not working

**Solution:** Check for typos in `defer_all_except`:

```python
# ❌ Wrong: Tool name doesn't match
defer_all_except=["ls", "list_directory"]  # Tool is actually called "ls"

# ✅ Correct: Exact match
defer_all_except=["ls", "cd"]
```

### Issue: Can't find tools with search

**Problem:** `tool_search` returns no results

**Solution:** Improve search keywords:

```python
# Add custom keyword function
def better_keywords(tool_name: str, tool_def: dict) -> list[str]:
    keywords = [tool_name.lower()]

    # Extract from description
    if desc := tool_def.get("description"):
        words = desc.lower().split()
        keywords.extend([w for w in words if len(w) > 4])

    return list(set(keywords))  # Deduplicate

await register_mcp_tools(
    stream_manager=stream_manager,
    defer_loading=True,
    search_keywords_fn=better_keywords,
)
```

## Performance

### Memory Usage

- **Deferred tools**: Only metadata (~1KB per tool)
- **Active tools**: Full MCPTool instance (~10KB per tool)
- **Savings**: 90% memory reduction for deferred tools

### Search Performance

- **Query time**: < 1ms for 1000 tools
- **Algorithm**: Simple keyword matching + relevance scoring
- **Scalability**: O(n) where n = deferred tools

### Loading Time

- **First load**: ~100ms (creates MCPTool instance)
- **Subsequent calls**: Instant (tool is cached)
- **No overhead**: After loading, performance is identical to eager loading

## See Also

- [Advanced Tool Use Guide](./advanced_tool_use.md) - General deferred loading
- [Example: MCP Deferred Loading](../examples/mcp_deferred_loading_example.py)
- [Example: Working Deferred Loading](../examples/working_deferred_example.py)
- [MCP Tool Documentation](./mcp_tools.md)
