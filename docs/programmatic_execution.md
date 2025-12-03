# Programmatic Tool Execution

> Enable LLMs to orchestrate tools through code instead of sequential API calls

## Overview

**Programmatic execution** allows LLMs to write Python code that directly calls your tools, rather than making sequential API requests. This provides:

- **37% token reduction** on complex workflows
- **Massive latency improvements** by eliminating inference passes
- **Better accuracy** through code-based orchestration
- **Parallel execution** of independent tool calls
- **In-memory data processing** without context pollution

## How It Works

### Traditional Sequential Approach

```
User: "Analyze sales data for top 10 customers"

API Call 1: get_sales_data()
→ Returns 1000 rows (20K tokens)

API Call 2: filter_top_customers(data)
→ Returns 10 rows (2K tokens)

API Call 3: analyze_trends(filtered_data)
→ Returns analysis (3K tokens)

Total: 3 API calls, 25K tokens, ~10 seconds
```

### Programmatic Approach

```
User: "Analyze sales data for top 10 customers"

API Call 1: LLM writes code:
```python
# Get data
sales = await get_sales_data()

# Process in memory (no token cost!)
top_10 = sorted(sales, key=lambda x: x['revenue'], reverse=True)[:10]

# Analyze
analysis = await analyze_trends(top_10)

return analysis
```

Total: 1 API call, 3K tokens (85% reduction!), ~2 seconds
```

## Provider Support

### Anthropic Claude

Claude has **built-in code execution** via the `code_execution_20250825` tool.

**Enable via:**
```python
tool_spec = ToolSpec(
    name="get_sales_data",
    description="Fetch sales data from database",
    parameters={...},
    allowed_callers=["code_execution_20250825"],  # ← Key field
)
```

**API Usage:**
```python
import anthropic

client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-sonnet-4.5-20250514",
    max_tokens=1024,
    betas=["advanced-tool-use-2025-11-20"],  # ← Required beta header
    tools=[
        tool_spec.to_anthropic(),  # Includes allowed_callers
        # ... other tools
    ],
    messages=[{
        "role": "user",
        "content": "Analyze sales data for top 10 customers"
    }]
)
```

### OpenAI (via Custom Sandbox)

OpenAI doesn't have built-in code execution for tool orchestration, but you can implement it:

```python
from chuk_tool_processor.execution.code_sandbox import CodeSandbox

# 1. LLM generates code
code = """
sales = await get_sales_data()
top_10 = sorted(sales, key=lambda x: x['revenue'], reverse=True)[:10]
analysis = await analyze_trends(top_10)
return analysis
"""

# 2. Execute in sandbox with tool access
sandbox = CodeSandbox(registry=your_tool_registry)
result = await sandbox.execute(code)
```

### Any LLM (Self-Hosted Sandbox)

Works with any LLM that can generate Python code:

```python
# 1. Prompt LLM to write code
prompt = f"""
Available tools:
{format_tools_for_llm(registry)}

Write Python code to: {user_request}
"""

# 2. LLM generates code
code = await llm.generate(prompt)

# 3. Execute safely
result = await code_sandbox.execute(code, tools=registry)
```

## When to Use Programmatic Execution

✅ **Good Use Cases:**
- Processing large datasets (>1000 items)
- Multi-step workflows (3+ dependent operations)
- Parallel tool calls across many items
- Data aggregation/transformation
- Iterative operations (loops over results)

❌ **Don't Use When:**
- Single tool call is sufficient
- Real-time user interaction needed during execution
- Tool results need to influence next reasoning step
- Security/sandbox constraints prohibit code execution

## Security Considerations

### Sandboxing Requirements

**CRITICAL**: Never execute LLM-generated code without sandboxing!

Minimum requirements:
- Restricted Python environment (no `os`, `sys`, `subprocess`)
- Network access controls
- File system isolation
- Resource limits (CPU, memory, time)
- Tool allowlist (only registered tools accessible)

### Example Sandbox Setup

```python
import RestrictedPython

def create_safe_globals(tool_registry):
    """Create restricted execution environment with tool access."""

    # Only allow safe builtins
    safe_builtins = {
        'len': len,
        'str': str,
        'int': int,
        'float': float,
        'list': list,
        'dict': dict,
        'sorted': sorted,
        'sum': sum,
        'min': min,
        'max': max,
        # ... other safe builtins
    }

    # Add tool access
    async def call_tool(name, **kwargs):
        tool = await tool_registry.get_tool(name)
        if tool is None:
            raise ValueError(f"Tool {name} not found")
        return await tool.execute(**kwargs)

    return {
        '__builtins__': safe_builtins,
        'call_tool': call_tool,
    }
```

## Implementation Guide

### Step 1: Mark Tools as Programmatic

```python
from chuk_tool_processor.registry import register_tool
from chuk_tool_processor.models.validated_tool import ValidatedTool

@register_tool(
    namespace="sales",
    tags=["database", "sales"],
    # Enable programmatic access
    allowed_callers=["code_execution_20250825", "sandbox"],
)
class GetSalesDataTool(ValidatedTool):
    """Fetch sales data from database."""

    class Arguments(BaseModel):
        start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
        end_date: str = Field(..., description="End date (YYYY-MM-DD)")

    class Result(BaseModel):
        rows: list[dict] = Field(..., description="Sales records")

    async def _execute(self, start_date: str, end_date: str) -> dict:
        # Fetch from database
        rows = await db.query(
            "SELECT * FROM sales WHERE date BETWEEN ? AND ?",
            start_date, end_date
        )
        return {"rows": rows}
```

### Step 2: Export with Programmatic Support

```python
from chuk_tool_processor.registry import get_default_registry

registry = await get_default_registry()

# Get all tools that support programmatic execution
programmatic_tools = []
for tool_info in await registry.list_tools():
    metadata = await registry.get_metadata(tool_info.name, tool_info.namespace)

    if metadata.allowed_callers and "code_execution_20250825" in metadata.allowed_callers:
        # Export for Anthropic
        spec = ToolSpec.from_metadata(metadata)
        programmatic_tools.append(spec.to_anthropic())
```

### Step 3: Handle Code Execution (Anthropic)

When Claude returns code execution results, they come in this format:

```python
{
    "type": "tool_use",
    "id": "toolu_01...",
    "name": "code_execution_20250825",
    "input": {
        "code": "...",  # The Python code Claude wrote
        "tools": ["get_sales_data", "analyze_trends"],  # Tools it plans to use
    }
}
```

You don't execute this yourself - Claude's code execution environment handles it. You just need to mark your tools as available.

## Best Practices

### 1. Clear Tool Documentation

Tools used programmatically need excellent docs:

```python
@register_tool(
    namespace="sales",
    allowed_callers=["code_execution_20250825"],
)
class GetSalesDataTool(ValidatedTool):
    """
    Fetch sales data from database.

    Returns: List of sales records with fields:
        - customer_id (str): Customer identifier
        - revenue (float): Revenue in USD
        - date (str): Sale date in YYYY-MM-DD format
        - product_id (str): Product identifier

    Example usage in code:
        sales = await get_sales_data(start_date="2024-01-01", end_date="2024-12-31")
        top_customer = max(sales, key=lambda x: x['revenue'])
    """
```

### 2. Return Structured Data

Make data easy to work with in code:

```python
# ✅ Good: Structured, easy to manipulate
class Result(BaseModel):
    rows: list[dict[str, Any]] = Field(..., description="Sales records")
    total_count: int = Field(..., description="Total number of records")

# ❌ Bad: Unstructured text
class Result(BaseModel):
    message: str = Field(..., description="Human-readable summary")
```

### 3. Document Return Formats

From Anthropic's best practices:

> "Clear documentation of return structures helps Claude write correct parsing logic."

```python
"""
Returns:
    {
        "rows": [
            {"customer_id": "C123", "revenue": 1500.00, "date": "2024-01-15"},
            {"customer_id": "C456", "revenue": 2300.50, "date": "2024-01-16"},
            ...
        ],
        "total_count": 1000
    }
"""
```

### 4. Idempotent Operations

Tools used in code should be safe to retry:

```python
@register_tool(
    namespace="sales",
    allowed_callers=["code_execution_20250825"],
    capabilities=[ToolCapability.IDEMPOTENT],  # Mark as safe to retry
)
class GetSalesDataTool(ValidatedTool):
    """Read-only data fetch - safe to call multiple times."""
```

## Examples

### Example 1: Data Aggregation

**User**: "What's the total revenue per product category?"

**Claude's Code**:
```python
# Fetch sales data
sales = await get_sales_data(start_date="2024-01-01", end_date="2024-12-31")

# Group by category
from collections import defaultdict
category_revenue = defaultdict(float)

for sale in sales['rows']:
    product = await get_product(product_id=sale['product_id'])
    category_revenue[product['category']] += sale['revenue']

# Format results
results = [
    {"category": cat, "total_revenue": rev}
    for cat, rev in sorted(category_revenue.items(), key=lambda x: x[1], reverse=True)
]

return {"categories": results}
```

**Savings**: ~15K tokens (intermediate product lookups stay in memory)

### Example 2: Parallel Processing

**User**: "Check inventory status for all low-stock products"

**Claude's Code**:
```python
import asyncio

# Get low stock products
products = await get_low_stock_products(threshold=10)

# Check each product's status in parallel
async def check_product(product_id):
    inventory = await get_inventory_status(product_id=product_id)
    supplier = await get_supplier_info(supplier_id=inventory['supplier_id'])
    return {
        "product_id": product_id,
        "stock": inventory['quantity'],
        "supplier": supplier['name'],
        "lead_time": supplier['lead_time_days']
    }

# Execute all checks concurrently
results = await asyncio.gather(*[
    check_product(p['id']) for p in products['items']
])

return {"statuses": results}
```

**Savings**: Executes in parallel instead of 20+ sequential API calls

### Example 3: Iterative Processing

**User**: "Find the first customer who made a purchase over $10,000"

**Claude's Code**:
```python
# Fetch customers sorted by total purchases
customers = await get_top_customers(limit=100)

# Check each until we find one meeting criteria
for customer in customers['rows']:
    purchases = await get_customer_purchases(customer_id=customer['id'])

    # Check if any single purchase exceeds threshold
    big_purchase = next(
        (p for p in purchases['items'] if p['amount'] > 10000),
        None
    )

    if big_purchase:
        return {
            "customer": customer,
            "purchase": big_purchase
        }

return {"message": "No customer found with purchase > $10,000"}
```

**Savings**: Stops early, doesn't fetch all purchases for all customers

## Troubleshooting

### Issue: Tool not available in code execution

**Problem**: Claude says tool isn't available

**Solution**: Ensure `allowed_callers` includes the execution environment:

```python
# ✅ Correct
allowed_callers=["code_execution_20250825"]

# ❌ Wrong - not marked for programmatic use
allowed_callers=None  # or missing entirely
```

### Issue: Code execution timeout

**Problem**: Code takes too long to execute

**Solutions**:
1. Add pagination to data fetching tools
2. Reduce batch sizes
3. Increase timeout (if provider supports it)
4. Break into smaller sub-tasks

### Issue: Sandbox security errors

**Problem**: Code tries to access restricted functionality

**Solution**: Ensure sandbox only exposes safe operations:
```python
# ✅ Safe
safe_builtins = {'len', 'str', 'sorted', 'sum'}

# ❌ Dangerous
unsafe_builtins = {'eval', 'exec', 'open', '__import__'}
```

## See Also

- [Advanced Tool Use Guide](./advanced_tool_use.md) - Deferred loading and tool search
- [Tool Examples](./tool_examples.md) - Best practices for tool documentation
- [Security Guide](./security.md) - Sandboxing and execution safety
