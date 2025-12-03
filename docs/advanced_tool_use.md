# Advanced Tool Use: Dynamic Tool Binding

> Breaking through the 128 function limit with deferred loading

## Overview

Most LLM APIs limit you to 128 functions per request. With **deferred tool loading**, you can scale to **unlimited tools** by loading them dynamically on-demand.

This implements the patterns described in [Anthropic's Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use) blog post.

## The Problem

```python
# You have 500 database tools
tools = [
    postgres_query, postgres_insert, postgres_update, postgres_delete,
    mongo_find, mongo_insert, mongo_aggregate,
    # ... 493 more tools ...
]

# ❌ ERROR: Most APIs limit to 128 tools
response = client.messages.create(
    model="claude-3-5-sonnet",
    tools=tools  # Too many!
)
```

## The Solution: Dynamic Tool Binding

### 1. Mark Tools as Deferred

```python
from chuk_tool_processor.registry import register_tool
from chuk_tool_processor.models.validated_tool import ValidatedTool

# Core tools: Always loaded (< 128)
@register_tool(namespace="core")
class CalculatorTool(ValidatedTool):
    pass

# Deferred tools: Loaded on-demand
@register_tool(
    namespace="postgres",
    defer_loading=True,  # 🔑 Key feature!
    search_keywords=["database", "sql", "query", "postgres"],
    tags={"database", "sql"}
)
class PostgresQueryTool(ValidatedTool):
    pass
```

### 2. Use Tool Search

The `ToolSearchTool` is automatically registered in the `system` namespace:

```python
from chuk_tool_processor.registry import get_default_registry

registry = await get_default_registry()

# Search for tools matching "postgres query"
matches = await registry.search_deferred_tools(
    query="postgres query",
    tags=["database"],
    limit=5
)

# Load matched tools
for tool_meta in matches:
    await registry.load_deferred_tool(tool_meta.name, tool_meta.namespace)
```

### 3. Bind Only Active Tools to API

```python
# Get only currently loaded tools
registry = await get_default_registry()
active_tools = await registry.get_active_tools()

# Convert to API format
tool_schemas = []
for tool_info in active_tools:
    tool_class = await registry.get_tool(tool_info.name, tool_info.namespace)
    tool_schemas.append(tool_class.to_anthropic())

# Call API with dynamic tool list
response = client.messages.create(
    model="claude-3-5-sonnet",
    tools=tool_schemas,  # Only loaded tools!
    messages=messages
)
```

## Complete Workflow

```
┌─────────────────────────────────────────────────────────┐
│ Tool Registry                                           │
│  • 5 core tools (always loaded)                         │
│  • 495 deferred tools (loaded on demand)                │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ API Call #1: Initial Request                            │
│ Tools: [tool_search, calculator, web_search]            │
│ Count: 3 tools (well under 128 limit!)                  │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ Claude: "I need PostgreSQL tools"                       │
│ Action: tool_search(query="postgres query")             │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ Tool Search Returns:                                    │
│  • postgres_query                                       │
│  • postgres_insert                                      │
│  • postgres_transaction                                 │
│ Status: ✅ Tools now loaded                             │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ API Call #2: With New Tools                             │
│ Tools: [tool_search, calculator, web_search,            │
│         postgres_query, postgres_insert,                │
│         postgres_transaction]                           │
│ Count: 6 tools                                          │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ Claude: Uses postgres_query(sql="SELECT...")            │
│ Status: ✅ Success!                                      │
└─────────────────────────────────────────────────────────┘
```

## API Reference

### Decorator Parameters

```python
@register_tool(
    name: str | None = None,
    namespace: str = "default",
    defer_loading: bool = False,  # Enable deferred loading
    search_keywords: list[str] | None = None,  # Keywords for search
    allowed_callers: list[str] | None = None,  # ['claude', 'programmatic']
    **metadata
)
```

### Registry Methods

```python
# Search deferred tools
await registry.search_deferred_tools(
    query: str,
    tags: list[str] | None = None,
    limit: int = 5
) -> list[ToolMetadata]

# Load a deferred tool
await registry.load_deferred_tool(
    name: str,
    namespace: str = "default"
) -> Any

# Get active (loaded) tools
await registry.get_active_tools(
    namespace: str | None = None
) -> list[ToolInfo]

# Get deferred (not loaded) tools
await registry.get_deferred_tools(
    namespace: str | None = None
) -> list[ToolInfo]
```

## Real-World Examples

### Example 1: Database Tool Library

```python
# 500 database tools across 4 databases
@register_tool(namespace="postgres", defer_loading=True, search_keywords=["postgres", "sql", "query"])
class PostgresQueryTool(ValidatedTool):
    pass

# 199 more postgres tools...

@register_tool(namespace="mongodb", defer_loading=True, search_keywords=["mongo", "nosql"])
class MongoFindTool(ValidatedTool):
    pass

# 149 more mongo tools...

# User: "Query my PostgreSQL users table"
# → tool_search finds postgres tools
# → Loads only 3-5 postgres tools
# → Total tools sent to API: < 10
```

### Example 2: Data Processing Pipeline

```python
# Hundreds of specialized data processing tools
@register_tool(namespace="data", defer_loading=True, search_keywords=["csv", "parse"])
class CSVParserTool(ValidatedTool):
    pass

@register_tool(namespace="data", defer_loading=True, search_keywords=["json", "validate"])
class JSONValidatorTool(ValidatedTool):
    pass

@register_tool(namespace="ml", defer_loading=True, search_keywords=["predict", "model"])
class MLPredictTool(ValidatedTool):
    pass

# User workflow loads tools progressively:
# 1. CSV parsing task → loads CSV tools
# 2. JSON validation task → loads JSON tools
# 3. ML prediction task → loads ML tools
# Each step adds only needed tools
```

## Benefits

### ✅ Unlimited Tools
- **Before**: Limited to 128 tools
- **After**: Thousands of tools, loaded on-demand

### ✅ Reduced Token Usage
- **Before**: 128 tool schemas in every request
- **After**: 5-10 tool schemas, only what's needed

### ✅ Faster Response Times
- Smaller tool lists = faster API calls
- Less parsing overhead for Claude

### ✅ Better Organization
- Namespace-based organization
- Clear separation between core and specialized tools
- Searchable tool metadata

## Migration Guide

### Step 1: Identify Core vs Specialized Tools

```python
# Core tools (use frequently, < 10 tools)
CORE_TOOLS = [
    "tool_search",      # Required for discovery
    "calculator",
    "web_search",
    "file_read",
]

# Specialized tools (use occasionally, mark as deferred)
SPECIALIZED_TOOLS = [
    "postgres_*",       # 200 tools
    "mongodb_*",        # 150 tools
    "ml_*",            # 100 tools
    # etc...
]
```

### Step 2: Mark Tools as Deferred

```python
# Before
@register_tool(namespace="postgres")
class PostgresQueryTool(ValidatedTool):
    pass

# After
@register_tool(
    namespace="postgres",
    defer_loading=True,  # ← Add this
    search_keywords=["postgres", "sql", "query"],  # ← And this
)
class PostgresQueryTool(ValidatedTool):
    pass
```

### Step 3: Update API Integration

```python
async def get_tools_for_api():
    """Get tools to send to LLM API."""
    registry = await get_default_registry()

    # Only get active (loaded) tools
    active_tools = await registry.get_active_tools()

    # Convert to API format
    return [
        await get_tool_schema(tool.name, tool.namespace)
        for tool in active_tools
    ]
```

### Step 4: Handle Tool Search Calls

```python
# When Claude calls tool_search, it auto-loads tools
# Just process the response and make a new API call with updated tools

if tool_call.name == "tool_search":
    # Tool search automatically loaded new tools
    # Get updated tool list for next API call
    updated_tools = await get_tools_for_api()

    # Continue conversation with expanded tool set
    response = client.messages.create(
        model="claude-3-5-sonnet",
        tools=updated_tools,  # Now includes newly loaded tools
        messages=messages
    )
```

## Best Practices

### 1. Choose Good Search Keywords

```python
# ❌ Bad: Too generic
search_keywords=["tool", "data"]

# ✅ Good: Specific and discoverable
search_keywords=["postgres", "sql", "query", "database", "select"]
```

### 2. Use Descriptive Namespaces

```python
# ❌ Bad: Everything in default namespace
@register_tool(namespace="default", defer_loading=True)

# ✅ Good: Organized by domain
@register_tool(namespace="postgres", defer_loading=True)
@register_tool(namespace="mongodb", defer_loading=True)
@register_tool(namespace="ml", defer_loading=True)
```

### 3. Keep Core Tools Small

```python
# ✅ Aim for < 10 core tools
CORE_TOOLS = 5-10 tools

# Everything else should be deferred
DEFERRED_TOOLS = Unlimited!
```

### 4. Add Rich Descriptions

```python
@register_tool(
    namespace="postgres",
    defer_loading=True,
    search_keywords=["postgres", "query", "sql", "select"],
)
class PostgresQueryTool(ValidatedTool):
    """
    Execute PostgreSQL SELECT queries with advanced filtering.

    Supports:
    - Complex WHERE clauses
    - JOINs across tables
    - Aggregations (COUNT, SUM, AVG)
    - LIMIT and OFFSET for pagination
    """
    pass
```

## Performance Considerations

### Tool Search is Fast
- Keyword matching is O(n) where n = deferred tools
- Typically < 1ms for 1000 tools

### Lazy Loading is Instant
- Tools are imported on first use
- Cached after loading
- Zero overhead for subsequent uses

### Token Savings
- 85% reduction in tool schema tokens (from Anthropic's blog)
- More context available for actual conversation

## Troubleshooting

### Issue: Tools not found by search

**Solution**: Improve search keywords

```python
# Add more specific keywords
@register_tool(
    search_keywords=[
        "postgres", "postgresql",  # Database name variants
        "query", "select", "sql",  # Operation types
        "database", "db", "rdbms"  # General terms
    ]
)
```

### Issue: Too many tools being loaded

**Solution**: Refine search queries

```python
# Instead of generic search
await registry.search_deferred_tools("database")  # Loads too many

# Use specific search
await registry.search_deferred_tools("postgres query")  # Loads only what's needed
```

### Issue: Import errors when loading deferred tools

**Solution**: Ensure import_path is correct

```python
# The decorator auto-generates import_path
# For manual override:
@register_tool(
    defer_loading=True,
    metadata={"import_path": "my_package.tools.MyTool"}
)
```

## See Also

- [Anthropic Advanced Tool Use Blog Post](https://www.anthropic.com/engineering/advanced-tool-use)
- [Example: Dynamic Tool Binding](../examples/dynamic_tool_binding_example.py)
- [Example: Deferred Tools](../src/sample_tools/deferred_example_tool.py)
- [Tests: Deferred Loading](../tests/test_deferred_loading.py)
