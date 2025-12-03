# Tool Use Examples

> Improve LLM tool calling accuracy from 72% to 90% with concrete usage examples

## Overview

**Tool Use Examples** provide concrete demonstrations of how to call your tools, going beyond what JSON schemas can express. According to Anthropic's research, adding examples improves accuracy from 72% to 90% on complex parameter handling.

## Why Examples Matter

JSON schemas describe **what is possible**, but examples show **what is typical**:

### Schema Alone (72% Accuracy)
```json
{
  "name": "create_event",
  "parameters": {
    "type": "object",
    "properties": {
      "title": {"type": "string"},
      "start_date": {"type": "string"},
      "end_date": {"type": "string", "optional": true},
      "attendees": {"type": "array", "items": {"type": "string"}},
      "recurrence": {"type": "string", "enum": ["daily", "weekly", "monthly"]}
    }
  }
}
```

**Problems**:
- What date format? ISO 8601? Unix timestamp?
- Is `end_date` really optional for all events?
- How should attendees be formatted? Email? Name? Both?
- When is `recurrence` used vs omitted?

### Schema + Examples (90% Accuracy)
```python
ToolSpec(
    name="create_event",
    parameters={...},  # Same schema
    examples=[
        {
            "input": {
                "title": "Team Standup",
                "start_date": "2024-01-15T09:00:00Z",
                "attendees": ["alice@company.com", "bob@company.com"],
                "recurrence": "daily"
            },
            "description": "Daily recurring meeting"
        },
        {
            "input": {
                "title": "Project Deadline",
                "start_date": "2024-03-01T23:59:59Z",
                "attendees": []
            },
            "description": "Single event with no attendees"
        },
        {
            "input": {
                "title": "Conference",
                "start_date": "2024-06-10T09:00:00Z",
                "end_date": "2024-06-12T17:00:00Z",
                "attendees": ["team@company.com"]
            },
            "description": "Multi-day event with mailing list"
        }
    ]
)
```

**Benefits**:
- ✅ Shows ISO 8601 date format
- ✅ Demonstrates optional `end_date` usage
- ✅ Shows email format for attendees
- ✅ Illustrates when to use/omit `recurrence`

## When to Add Examples

### ✅ Always Add Examples For:

1. **Complex Nested Structures**
   ```python
   # Hard to understand from schema alone
   "filters": {
       "type": "object",
       "properties": {
           "conditions": {
               "type": "array",
               "items": {
                   "type": "object",
                   "properties": {
                       "field": {"type": "string"},
                       "operator": {"type": "string"},
                       "value": {}
                   }
               }
           },
           "logic": {"type": "string", "enum": ["AND", "OR"]}
       }
   }
   ```

2. **Domain-Specific Conventions**
   - Date/time formats (ISO 8601 vs Unix timestamps)
   - ID formats (UUIDs vs integers vs strings)
   - Currency handling ($100 vs 100.00 vs 10000 cents)
   - Phone numbers (+1-555-0123 vs 5550123)

3. **Optional Parameter Patterns**
   - When are optional params actually needed?
   - Which combinations are valid?
   - What are the defaults?

4. **Ambiguous Enums**
   - When to use each enum value
   - Real-world scenarios for each option

### ❌ Skip Examples For:

- Simple CRUD operations with obvious parameters
- Tools with 1-2 required string/number parameters
- Self-explanatory operations (`add(x: int, y: int)`)

## Example Structure

Each example should have:

```python
{
    "input": {
        # Actual parameter values that would be passed
        "param1": "value1",
        "param2": 123
    },
    "description": "Brief explanation of this use case",  # Optional but recommended
    "output": {  # Optional - show expected result
        "result": "..."
    }
}
```

## Implementation

### Using ToolSpec

```python
from chuk_tool_processor.models.tool_spec import ToolSpec

spec = ToolSpec(
    name="search_products",
    description="Search product catalog with filters",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "category": {"type": "string", "optional": True},
            "min_price": {"type": "number", "optional": True},
            "max_price": {"type": "number", "optional": True},
            "in_stock_only": {"type": "boolean", "default": False}
        },
        "required": ["query"]
    },
    examples=[
        {
            "input": {
                "query": "wireless headphones",
                "category": "electronics",
                "max_price": 200,
                "in_stock_only": True
            },
            "description": "Search with category filter and price cap"
        },
        {
            "input": {
                "query": "laptop"
            },
            "description": "Simple search with just query"
        },
        {
            "input": {
                "query": "office chair",
                "min_price": 200,
                "max_price": 500,
                "in_stock_only": True
            },
            "description": "Price range search for in-stock items"
        }
    ]
)

# Export to any provider
anthropic_format = spec.to_anthropic()  # Includes examples
openai_format = spec.to_openai()         # Includes examples
mcp_format = spec.to_mcp()               # Includes examples
```

### Using ValidatedTool

```python
from chuk_tool_processor.models.validated_tool import ValidatedTool
from chuk_tool_processor.registry import register_tool
from pydantic import BaseModel, Field

@register_tool(
    namespace="products",
    examples=[
        {
            "input": {
                "query": "wireless headphones",
                "category": "electronics",
                "max_price": 200,
                "in_stock_only": True
            },
            "description": "Category and price filtered search"
        },
        {
            "input": {"query": "laptop"},
            "description": "Basic search"
        }
    ]
)
class SearchProductsTool(ValidatedTool):
    """Search product catalog with optional filters."""

    class Arguments(BaseModel):
        query: str = Field(..., description="Search query")
        category: str | None = Field(None, description="Product category")
        min_price: float | None = Field(None, description="Minimum price in USD")
        max_price: float | None = Field(None, description="Maximum price in USD")
        in_stock_only: bool = Field(False, description="Only show in-stock items")

    class Result(BaseModel):
        products: list[dict] = Field(..., description="Matching products")
        total_count: int = Field(..., description="Total matches")

    async def _execute(self, query: str, **kwargs) -> dict:
        # Implementation
        pass
```

## Best Practices

### 1. Show Variety

Include examples that demonstrate:

```python
examples=[
    # Minimal - only required params
    {
        "input": {"query": "laptop"},
        "description": "Minimal search"
    },

    # Typical - common use case
    {
        "input": {
            "query": "laptop",
            "category": "electronics",
            "in_stock_only": True
        },
        "description": "Typical filtered search"
    },

    # Maximal - all params
    {
        "input": {
            "query": "laptop",
            "category": "electronics",
            "min_price": 500,
            "max_price": 2000,
            "in_stock_only": True
        },
        "description": "Fully specified search"
    }
]
```

### 2. Use Realistic Data

```python
# ✅ Good - realistic values
{
    "input": {
        "customer_id": "cust_7h2j9k3m",
        "email": "alice@example.com",
        "purchase_date": "2024-01-15T14:30:00Z"
    }
}

# ❌ Bad - generic placeholders
{
    "input": {
        "customer_id": "12345",
        "email": "user@email.com",
        "purchase_date": "DATE_HERE"
    }
}
```

### 3. Show Edge Cases

```python
examples=[
    # Normal case
    {
        "input": {"items": ["item1", "item2", "item3"]},
        "description": "Multiple items"
    },

    # Edge: empty list
    {
        "input": {"items": []},
        "description": "Empty list (returns empty result)"
    },

    # Edge: single item
    {
        "input": {"items": ["only_one"]},
        "description": "Single item"
    }
]
```

### 4. Document Correlations

When parameters affect each other:

```python
examples=[
    {
        "input": {
            "payment_method": "credit_card",
            "card_number": "4111111111111111",
            "cvv": "123",
            "expiry": "12/25"
        },
        "description": "Credit card requires card details"
    },
    {
        "input": {
            "payment_method": "bank_transfer",
            "account_number": "123456789",
            "routing_number": "987654321"
        },
        "description": "Bank transfer needs different fields"
    },
    {
        "input": {
            "payment_method": "paypal",
            "paypal_email": "user@example.com"
        },
        "description": "PayPal only needs email"
    }
]
```

### 5. Keep It Concise

```python
# ✅ Good - 1-5 examples covering key patterns
examples=[
    {"input": {...}, "description": "Basic usage"},
    {"input": {...}, "description": "With optional filters"},
    {"input": {...}, "description": "Edge case: empty result"}
]

# ❌ Too many - diminishing returns
examples=[...20 examples...]  # Excessive, adds noise
```

## Real-World Examples

### Example 1: Database Query Tool

```python
@register_tool(
    namespace="database",
    examples=[
        {
            "input": {
                "query": "SELECT * FROM users WHERE age > 25",
                "params": None
            },
            "description": "Simple SELECT without parameters"
        },
        {
            "input": {
                "query": "SELECT * FROM users WHERE email = ? AND active = ?",
                "params": ["alice@example.com", True]
            },
            "description": "Parameterized query for safety"
        },
        {
            "input": {
                "query": "INSERT INTO orders (user_id, total) VALUES (?, ?)",
                "params": [123, 99.99]
            },
            "description": "INSERT with parameters"
        }
    ]
)
class DatabaseQueryTool(ValidatedTool):
    """Execute SQL query against database."""
    # ...
```

### Example 2: Date Range Tool

```python
@register_tool(
    namespace="analytics",
    examples=[
        {
            "input": {
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "timezone": "UTC"
            },
            "description": "Month-long report in UTC"
        },
        {
            "input": {
                "start_date": "2024-01-15T09:00:00Z",
                "end_date": "2024-01-15T17:00:00Z",
                "timezone": "America/New_York"
            },
            "description": "Single day with timezone"
        }
    ]
)
class GenerateReportTool(ValidatedTool):
    """Generate analytics report for date range."""
    # ...
```

### Example 3: Complex Filtering

```python
@register_tool(
    namespace="crm",
    examples=[
        {
            "input": {
                "filters": {
                    "conditions": [
                        {"field": "status", "operator": "equals", "value": "active"},
                        {"field": "revenue", "operator": "greater_than", "value": 10000}
                    ],
                    "logic": "AND"
                },
                "sort": {"field": "created_at", "order": "desc"},
                "limit": 50
            },
            "description": "Active high-value customers, newest first"
        },
        {
            "input": {
                "filters": {
                    "conditions": [
                        {"field": "tags", "operator": "contains", "value": "vip"}
                    ]
                },
                "limit": 100
            },
            "description": "Simple tag filter"
        }
    ]
)
class SearchCustomersTool(ValidatedTool):
    """Search customers with complex filters."""
    # ...
```

## Provider-Specific Notes

### Anthropic Claude

Anthropic's advanced tool use explicitly supports examples:

```python
# Enable via beta header
client.messages.create(
    model="claude-sonnet-4.5-20250514",
    betas=["advanced-tool-use-2025-11-20"],  # Required
    tools=[spec.to_anthropic()],  # Includes examples automatically
    ...
)
```

### OpenAI

OpenAI's function calling accepts examples in tool definitions:

```python
openai.chat.completions.create(
    model="gpt-4",
    tools=[spec.to_openai()],  # Includes examples automatically
    ...
)
```

### MCP Servers

MCP servers can include examples in tool definitions:

```python
{
    "name": "search_products",
    "description": "...",
    "inputSchema": {...},
    "examples": [...]  # Standard MCP field
}
```

## Measuring Impact

Track accuracy improvements:

```python
# Before examples
test_cases = load_test_cases()
accuracy_before = measure_tool_call_accuracy(test_cases)
# → 72% accuracy

# After adding examples
spec.examples = [...]
accuracy_after = measure_tool_call_accuracy(test_cases)
# → 90% accuracy (25% improvement!)
```

## See Also

- [Advanced Tool Use](./advanced_tool_use.md) - Deferred loading and tool search
- [Programmatic Execution](./programmatic_execution.md) - Code-based tool orchestration
- [API Reference](./api_reference.md) - Full ToolSpec documentation
