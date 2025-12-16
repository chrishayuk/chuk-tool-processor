# Dynamic Tool Discovery

When you have hundreds of tools, LLMs can't load all schemas upfront — context windows have limits. The discovery module provides intelligent search and on-demand tool loading.

---

## Overview

The discovery module bridges the gap between how LLMs naturally describe tools and how tools are actually named in code:

| LLM Request | Tool Name | How Discovery Helps |
|-------------|-----------|---------------------|
| "gaussian distribution" | `normal_cdf` | Synonym expansion |
| "find the average" | `calculate_mean` | Natural language matching |
| "multipley" | `multiply` | Fuzzy matching (typo tolerance) |
| "normalCdf" | `normal_cdf` | Alias resolution |

---

## Quick Start

### Basic Search

```python
from chuk_tool_processor.discovery import ToolSearchEngine

# Create and populate the search engine
engine = ToolSearchEngine()
engine.set_tools(my_tools)  # Any objects with name, namespace, description

# Search with natural language
results = engine.search("gaussian distribution cdf")

for r in results:
    print(f"{r.name}: score={r.score}, reasons={r.match_reasons}")
```

### Dynamic Provider Pattern

For LLM integration, use `BaseDynamicToolProvider` to give LLMs meta-tools for discovering and executing tools on-demand:

```python
from chuk_tool_processor.discovery import BaseDynamicToolProvider

class MyToolProvider(BaseDynamicToolProvider):
    def __init__(self, tools: list):
        super().__init__()
        self._tools = tools

    async def get_all_tools(self) -> list:
        return self._tools

    async def execute_tool(self, name: str, args: dict) -> dict:
        tool = next((t for t in self._tools if t.name == name), None)
        if tool:
            return {"success": True, "result": await tool.execute(**args)}
        return {"success": False, "error": f"Tool '{name}' not found"}

# Create provider
provider = MyToolProvider(my_tools)

# Get tool definitions for the LLM (5 meta-tools)
tools_for_llm = provider.get_dynamic_tools()
# Returns: list_tools, search_tools, get_tool_schema, get_tool_schemas, call_tool

# LLM can now discover and use tools
results = await provider.search_tools("calculate average")
schema = await provider.get_tool_schema("calculate_mean")
schemas = await provider.get_tool_schemas(["add", "multiply"])  # Batch fetch
result = await provider.call_tool("calculate_mean", {"values": [1, 2, 3]})
```

---

## Search Features

### 1. Synonym Expansion

The search engine knows common synonyms across many domains:

| Domain | Query Term | Also Matches |
|--------|------------|--------------|
| Statistics | gaussian | normal, bell |
| Statistics | cdf | cumulative, distribution |
| Statistics | mean | average, expected, mu |
| Math | sqrt | square, root |
| Math | add | sum, plus |
| Linear Algebra | matrix | matrices, array, tensor |
| Linear Algebra | transpose | flip, swap |
| Geometry | area | surface, size |
| Geometry | distance | length, magnitude, norm |
| File Ops | read | get, load, fetch, retrieve |
| File Ops | write | save, store, put |
| String Ops | concat | concatenate, join, merge |
| String Ops | split | separate, divide, tokenize |
| Network | http | request, api, fetch |
| Network | download | fetch, retrieve, get |
| Crypto | encrypt | encode, cipher, secure |
| Crypto | hash | digest, checksum, fingerprint |
| ML/AI | train | fit, learn, optimize |
| ML/AI | predict | infer, forecast, estimate |
| NLP | tokenize | split, segment, parse |
| NLP | sentiment | emotion, opinion, polarity |
| Image | resize | scale, transform, shrink |
| Audio | volume | gain, amplitude, level |

```python
# "gaussian cdf" expands to include "normal", "cumulative", etc.
results = engine.search("gaussian cdf")  # Finds normal_cdf
```

### 2. Natural Language Queries

LLMs often describe what they want rather than the exact function name:

```python
# Descriptive queries work
engine.search("find the average of numbers")  # → calculate_mean
engine.search("save data to disk")            # → write_file
engine.search("bell curve probability")       # → normal_pdf
```

### 3. Fuzzy Matching

Handles typos and close matches when exact matching fails:

```python
engine.search("noraml_cdf")      # → normal_cdf (typo in 'normal')
engine.search("multipley")       # → multiply (typo)
engine.search("calclate mean")   # → calculate_mean (typo)
```

### 4. Alias Resolution

Tools can be found by various name forms:

```python
# All of these find the same tool:
await provider.get_tool_schema("normal_cdf")       # Exact name
await provider.get_tool_schema("stats.normal_cdf") # With namespace
await provider.get_tool_schema("normalCdf")        # camelCase
await provider.get_tool_schema("normalcdf")        # No separators
```

### 5. Session Boosting

Recently used tools rank higher in search results:

```python
# Initial search
results = engine.search("calculate")
# [calculate_mean, calculate_std, ...]

# Record tool usage
engine.record_tool_use("calculate_std", success=True)
engine.advance_turn()

# Now calculate_std is boosted
results = engine.search("calculate")
# [calculate_std (boosted), calculate_mean, ...]
```

Session boosting considers:
- **Recency**: How recently the tool was used (decays over turns)
- **Success rate**: Tools that succeed get higher boosts
- **Call count**: Frequently used tools get logarithmic boosts

---

## Two-Stage Search Pipeline

The search engine uses a two-stage approach for optimal results:

```
Query: "gaussian distribution cdf"
        ↓
Stage 1: High Precision
├─ Extract keywords: [gaussian, distribution, cdf]
├─ Exact name token matches: +10 points
└─ Prefix matches: +5 points
        ↓
Stage 2: Expanded Search (if Stage 1 score < 10)
├─ Expand with synonyms: {gaussian, normal, bell, cdf, cumulative, ...}
├─ Description matching: +3 points
├─ Namespace matching: +2 points
├─ Parameter name matching: +1 point
└─ Domain penalty: ×0.5-1.0 for mismatched domains
        ↓
Stage 3: Fuzzy Fallback (if no results)
├─ String similarity matching
└─ Description word matching
        ↓
Fallback (if still no results)
└─ Return popular/short-named tools
```

### Scoring Weights

| Match Type | Points |
|------------|--------|
| Exact name token | 10 |
| Name prefix | 5 |
| Description token | 3 |
| Namespace token | 2 |
| Parameter name | 1 |

---

## SearchableTool Protocol

The discovery module uses duck typing. Any object with these attributes works:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class SearchableTool(Protocol):
    name: str
    namespace: str
    description: str | None = None
    parameters: dict | None = None
```

This means you can use:
- `ToolMetadata` from the registry
- `ToolInfo` from MCP
- Custom dataclasses or classes
- Simple dictionaries (with attribute access)

---

## Dynamic Tool Provider

### Meta-Tools Provided

The `BaseDynamicToolProvider` gives LLMs these 5 meta-tools:

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_tools` | List all available tools | `limit` (default: 50) |
| `search_tools` | Search by natural language | `query`, `limit` (default: 10) |
| `get_tool_schema` | Get full schema for a tool | `tool_name` |
| `get_tool_schemas` | Get schemas for multiple tools (batch) | `tool_names` (list) |
| `call_tool` | Execute a discovered tool | `tool_name`, + tool params |

### Implementation

```python
from chuk_tool_processor.discovery import BaseDynamicToolProvider, SearchResult

class MyProvider(BaseDynamicToolProvider[MyToolType]):
    """Custom dynamic tool provider."""

    async def get_all_tools(self) -> list[MyToolType]:
        """Return all available tools."""
        return self._tools

    async def execute_tool(self, name: str, args: dict) -> dict:
        """Execute a tool. Must return dict with 'success' and 'result'/'error'."""
        tool = self._find_tool(name)
        if not tool:
            return {"success": False, "error": f"Tool '{name}' not found"}

        try:
            result = await tool.execute(**args)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # Optional: Custom filtering
    def filter_search_results(
        self,
        results: list[SearchResult[MyToolType]],
    ) -> list[SearchResult[MyToolType]]:
        """Filter results based on context (auth, permissions, etc.)."""
        return [r for r in results if self._user_can_access(r.tool)]

    # Optional: Custom property extraction
    def get_tool_name(self, tool: MyToolType) -> str:
        """Override if your tools use different attribute names."""
        return tool.tool_name  # Instead of tool.name
```

### LLM Workflow

Typical LLM workflow with dynamic discovery:

```
1. LLM: "I need to calculate the average of these numbers: [1, 2, 3, 4, 5]"

2. LLM calls: search_tools(query="calculate average")
   → Returns: [{name: "calculate_mean", score: 16.0, ...}]

3. LLM calls: get_tool_schema(tool_name="calculate_mean")
   → Returns: {function: {name: "calculate_mean", parameters: {...}}}

4. LLM calls: call_tool(tool_name="calculate_mean", values=[1, 2, 3, 4, 5])
   → Returns: {success: true, result: 3.0}

5. LLM: "The average is 3.0"
```

### Response Format

All dynamic tool methods return a consistent response format:

**Success responses:**
```python
{
    "success": True,
    "result": <data>,      # The actual result data
    "count": 5,            # Optional: count of items
    "total_available": 100 # Optional: total items available
}
```

**Error responses:**
```python
{
    "success": False,
    "error": "Tool 'xyz' not found",
    "suggestions": ["xyz_tool", "xyzzy"]  # Optional: similar tools
}
```

**Batch responses (get_tool_schemas):**
```python
{
    "success": True,       # True if all succeeded
    "schemas": [...],      # Successfully fetched schemas
    "errors": [            # Failed fetches
        {"tool_name": "missing", "error": "Not found"}
    ],
    "count": 3             # Number of successful schemas
}
```

---

## Synonym Dictionary

Built-in synonyms for common domains (150+ mappings):

### Statistics / Probability
- normal ↔ gaussian, bell
- cdf ↔ cumulative, distribution
- pdf ↔ probability, density
- mean ↔ average, expected, mu
- std ↔ standard, deviation, sigma

### Math Operations
- add ↔ sum, plus
- multiply ↔ times, product
- sqrt ↔ square, root
- divide ↔ quotient
- min ↔ minimum, smallest
- max ↔ maximum, largest

### Linear Algebra
- matrix ↔ matrices, array, tensor
- vector ↔ array, list, tuple
- transpose ↔ flip, swap
- inverse ↔ invert, reciprocal
- dot ↔ inner, scalar

### Geometry
- area ↔ surface, size
- distance ↔ length, magnitude, norm
- angle ↔ degree, radian, rotation

### File Operations
- read ↔ get, load, fetch, retrieve
- write ↔ save, store, put
- delete ↔ remove, rm, erase
- list ↔ ls, dir, enumerate
- copy ↔ duplicate, clone

### String Operations
- concat ↔ concatenate, join, merge
- split ↔ separate, divide, tokenize
- trim ↔ strip, clean
- upper ↔ uppercase, capitalize
- lower ↔ lowercase, downcase

### Network / API
- http ↔ request, api, fetch
- get ↔ fetch, retrieve, request
- post ↔ send, submit, create
- download ↔ fetch, retrieve
- connect ↔ open, establish

### Database
- query ↔ select, sql, search
- insert ↔ add, create, put
- update ↔ modify, change, set
- table ↔ collection, entity

### Cryptography / Security
- encrypt ↔ encode, cipher, secure
- decrypt ↔ decode, decipher
- hash ↔ digest, checksum, fingerprint
- sign ↔ signature, verify
- key ↔ secret, password, credential

### Encoding / Compression
- compress ↔ zip, gzip, deflate
- decompress ↔ unzip, inflate
- encode ↔ serialize, marshal
- decode ↔ deserialize, unmarshal

### ML / AI
- train ↔ fit, learn, optimize
- predict ↔ infer, forecast, estimate
- model ↔ network, classifier
- accuracy ↔ precision, recall, score
- cluster ↔ group, segment

### NLP / Text
- tokenize ↔ split, segment, parse
- stem ↔ lemma, root, base
- sentiment ↔ emotion, opinion
- classify ↔ categorize, label

### Image / Graphics
- image ↔ picture, photo, graphic
- resize ↔ scale, transform
- crop ↔ trim, cut, clip
- rotate ↔ turn, spin, flip

### Audio
- audio ↔ sound, music
- volume ↔ gain, amplitude, level
- play ↔ start, resume

### Concurrency
- async ↔ asynchronous, await
- parallel ↔ concurrent, multithread
- lock ↔ mutex, semaphore
- thread ↔ worker, task

---

## Domain Detection

The search engine detects query domain and applies penalties for mismatched results:

```python
# Query for statistics, but tool is arithmetic
engine.search("probability distribution")
# normal_cdf: score=10.0 (statistics tool)
# add: score=5.0 × 0.5 = 2.5 (domain penalty applied)
```

Detected domains:
- `statistics`: normal, gaussian, probability, distribution, cdf, pdf
- `arithmetic`: add, subtract, multiply, divide
- `number_theory`: prime, factor, gcd, lcm
- `linear_algebra`: matrix, vector, transpose, determinant, eigenvalue
- `geometry`: circle, triangle, area, perimeter, volume
- `trigonometry`: sin, cos, tan, radians, degrees
- `file_operations`: file, read, write, directory, path
- `string_operations`: string, concat, split, trim, replace
- `network`: http, api, request, fetch, socket
- `database`: query, sql, select, insert, table
- `cryptography`: encrypt, decrypt, hash, sign, certificate
- `encoding`: base64, compress, encode, json, xml
- `machine_learning`: train, predict, model, accuracy, feature
- `nlp`: tokenize, stem, entity, sentiment, classify
- `image_processing`: image, pixel, resize, crop, filter
- `audio_processing`: audio, sound, sample, frequency, volume
- `concurrency`: async, parallel, thread, lock, mutex

---

## API Reference

### ToolSearchEngine

```python
class ToolSearchEngine(Generic[T]):
    def set_tools(self, tools: list[T]) -> None:
        """Cache tools and build search index."""

    def search(
        self,
        query: str,
        tools: list[T] | None = None,
        limit: int = 10,
        min_score: float = 0.0,
        use_session_boost: bool = True,
    ) -> list[SearchResult[T]]:
        """Search for tools matching the query."""

    def find_exact(self, name: str, tools: list[T] | None = None) -> T | None:
        """Find a tool by exact name or alias."""

    def record_tool_use(self, tool_name: str, success: bool = True) -> None:
        """Record tool usage for session boosting."""

    def advance_turn(self) -> None:
        """Advance turn counter (call at start of each user prompt)."""

    def reset_session(self) -> None:
        """Reset session statistics."""

    def get_session_boost(self, tool_name: str) -> float:
        """Get current session boost multiplier for a tool."""
```

### SearchResult

```python
@dataclass
class SearchResult(Generic[T]):
    tool: T                              # The matched tool
    score: float                         # Match score
    match_reasons: list[str]             # Why it matched

    @property
    def name(self) -> str: ...           # Tool name
    @property
    def namespace(self) -> str: ...      # Tool namespace
    @property
    def description(self) -> str | None: ...  # Tool description
```

### BaseDynamicToolProvider

```python
class BaseDynamicToolProvider(ABC, Generic[T]):
    # Required methods
    @abstractmethod
    async def get_all_tools(self) -> list[T]: ...

    @abstractmethod
    async def execute_tool(self, tool_name: str, arguments: dict) -> dict: ...

    # Main API
    def get_dynamic_tools(self) -> list[dict]:
        """Get tool definitions for the LLM."""

    async def list_tools(self, limit: int = 50) -> list[dict]: ...
    async def search_tools(self, query: str, limit: int = 10) -> list[dict]: ...
    async def get_tool_schema(self, tool_name: str) -> dict: ...
    async def get_tool_schemas(self, tool_names: list[str]) -> dict: ...  # Batch
    async def call_tool(self, tool_name: str, arguments: dict) -> dict: ...

    async def execute_dynamic_tool(self, tool_name: str, arguments: dict) -> dict:
        """Execute one of the 5 meta-tools."""

    def is_dynamic_tool(self, tool_name: str) -> bool:
        """Check if a name is a meta-tool."""

    def invalidate_cache(self) -> None:
        """Clear caches when tools change."""

    # Optional hooks
    def filter_search_results(self, results: list[SearchResult[T]]) -> list[SearchResult[T]]:
        """Override to filter/modify search results."""

    def get_tool_name(self, tool: T) -> str:
        """Override if your tools use different attribute."""

    def get_tool_namespace(self, tool: T) -> str:
        """Override if your tools use different attribute."""
```

### Convenience Functions

```python
from chuk_tool_processor.discovery import (
    tokenize,           # Split names into searchable tokens
    extract_keywords,   # Extract keywords from natural language
    expand_with_synonyms,  # Expand tokens with synonyms
    normalize_tool_name,   # Generate name variants for matching
    find_tool_by_alias,    # Find tool by any name variant
    search_tools,          # Convenience search function
    find_tool_exact,       # Find by exact name
)
```

---

## Examples

Run the demo:

```bash
python examples/07_discovery/dynamic_tools_demo.py
```

This demonstrates:
1. Synonym expansion
2. Natural language queries
3. Fuzzy matching for typos
4. Session boosting
5. Dynamic provider pattern
6. Alias resolution

---

## Best Practices

1. **Index tools once**: Call `set_tools()` once at startup, not per-request

2. **Track session usage**: Call `record_tool_use()` after successful executions to improve future searches

3. **Advance turns**: Call `advance_turn()` at the start of each user interaction to decay session boosts

4. **Reset sessions**: Call `reset_session()` when starting a new conversation

5. **Override hooks**: Use `filter_search_results()` to hide tools based on authentication or context

6. **Use natural descriptions**: Write tool descriptions that match how users think about the functionality

7. **Namespace consistently**: Use dotted names (`math.add`) for logical grouping

---

## Integration with ToolProcessor

The discovery module works alongside `ToolProcessor`:

```python
from chuk_tool_processor import ToolProcessor, create_registry
from chuk_tool_processor.discovery import BaseDynamicToolProvider

class IntegratedProvider(BaseDynamicToolProvider):
    def __init__(self, registry, processor):
        super().__init__()
        self._registry = registry
        self._processor = processor

    async def get_all_tools(self):
        return await self._registry.list_tools()

    async def execute_tool(self, name: str, args: dict) -> dict:
        # Use the processor for execution with all its features
        # (timeouts, retries, caching, rate limits)
        call = [{"tool": name, "arguments": args}]
        results = await self._processor.process(call)
        if results and results[0].error:
            return {"success": False, "error": results[0].error}
        return {"success": True, "result": results[0].result}

# Usage
registry = create_registry()
await registry.register_tool(Calculator, name="math.calculator")

async with ToolProcessor(
    registry=registry,
    enable_caching=True,
    enable_retries=True,
) as processor:
    provider = IntegratedProvider(registry, processor)

    # LLM uses discovery to find and call tools
    results = await provider.search_tools("calculate")
    result = await provider.call_tool("math.calculator", {"a": 1, "b": 2})
```
