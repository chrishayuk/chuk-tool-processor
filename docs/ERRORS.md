# Error Taxonomy

Complete reference for all error types and codes in CHUK Tool Processor.

## Overview

CHUK Tool Processor uses **machine-readable error codes** and **structured error categories** for all errors. This allows planners to make intelligent decisions about retries, fallbacks, and backpressure.

All errors inherit from `ToolProcessorError` and include:
- `code`: Machine-readable error code (ErrorCode enum)
- `category`: High-level error category (ErrorCategory enum)
- `message`: Human-readable error message
- `retryable`: Whether this error is generally retryable
- `retry_after_ms`: Suggested delay before retry (milliseconds)
- `details`: Additional structured error context
- `to_dict()`: Method for serialization (logging, monitoring)
- `to_error_info()`: Convert to `ErrorInfo` for ToolResult

---

## Structured Error Handling for Planners

The `ToolResult` model includes structured error information via the `error_info` field:

```python
from chuk_tool_processor.core.exceptions import ErrorCategory

results = await processor.process(calls)
for result in results:
    if result.error_info:
        match result.error_info.category:
            case ErrorCategory.RATE_LIMIT:
                # Slow down and retry after delay
                await asyncio.sleep(result.retry_after_ms / 1000)
                return await retry()

            case ErrorCategory.CIRCUIT_OPEN:
                # Service unhealthy - use fallback
                return await use_fallback_tool()

            case ErrorCategory.BULKHEAD_FULL:
                # System at capacity - backpressure
                return await queue_for_later()

            case ErrorCategory.TIMEOUT:
                # Retry with longer timeout
                return await retry(timeout=result.error_info.details.get("timeout", 30) * 2)

            case _ if not result.retryable:
                # Permanent failure - don't retry
                return await report_permanent_failure()
```

---

## Error Categories

High-level categories for planner decision-making:

| Category | Description | Retryable | Action |
|----------|-------------|-----------|--------|
| `RATE_LIMIT` | Too many requests | ✅ Yes (after delay) | Wait for `retry_after_ms`, then retry |
| `CIRCUIT_OPEN` | Service unhealthy | ✅ Yes (after delay) | Use fallback or wait for recovery |
| `BULKHEAD_FULL` | Concurrency limit hit | ✅ Yes (after delay) | Backpressure signal, queue work |
| `TIMEOUT` | Operation took too long | ✅ Yes | Retry, possibly with longer timeout |
| `EXECUTION` | Tool logic failed | ✅ Yes (if transient) | Retry if error is transient |
| `CONNECTION` | Network/transport error | ✅ Yes | Retry with backoff |
| `VALIDATION` | Bad input/output | ❌ No | Fix the request, don't retry |
| `NOT_FOUND` | Tool doesn't exist | ❌ No | Check tool name, don't retry |
| `CANCELLED` | Operation cancelled | ❌ No | Don't retry |
| `CONFIGURATION` | System misconfigured | ❌ No | Fix configuration |

---

## Error Code Reference

### Tool Registry Errors

| Error Code | Exception Class | When It Occurs |
|------------|----------------|----------------|
| `TOOL_NOT_FOUND` | `ToolNotFoundError` | Requested tool doesn't exist in registry |
| `TOOL_REGISTRATION_FAILED` | `ToolProcessorError` | Tool registration failed (duplicate name, invalid class) |

### Execution Errors

| Error Code | Exception Class | When It Occurs |
|------------|----------------|----------------|
| `TOOL_EXECUTION_FAILED` | `ToolExecutionError` | Tool execution raised an exception |
| `TOOL_TIMEOUT` | `ToolTimeoutError` | Tool exceeded execution timeout |
| `TOOL_CANCELLED` | `ToolProcessorError` | Tool execution was cancelled |

### Validation Errors

| Error Code | Exception Class | When It Occurs |
|------------|----------------|----------------|
| `TOOL_VALIDATION_ERROR` | `ToolValidationError` | Arguments or result failed Pydantic validation |
| `TOOL_ARGUMENT_ERROR` | `ToolProcessorError` | Invalid arguments passed to tool |
| `TOOL_RESULT_ERROR` | `ToolProcessorError` | Tool returned invalid result |

### Rate Limiting & Circuit Breaker

| Error Code | Exception Class | When It Occurs |
|------------|----------------|----------------|
| `TOOL_RATE_LIMITED` | `ToolRateLimitedError` | Tool call rate limit exceeded |
| `TOOL_CIRCUIT_OPEN` | `ToolCircuitOpenError` | Circuit breaker is open (too many failures) |
| `BULKHEAD_FULL` | `BulkheadFullError` | Concurrency limit exceeded |

### Parser Errors

| Error Code | Exception Class | When It Occurs |
|------------|----------------|----------------|
| `PARSER_ERROR` | `ParserError` | Failed to parse tool calls from input |
| `PARSER_INVALID_FORMAT` | `ParserError` | Input format doesn't match any parser |

### MCP Errors

| Error Code | Exception Class | When It Occurs |
|------------|----------------|----------------|
| `MCP_CONNECTION_FAILED` | `MCPConnectionError` | Failed to connect to MCP server |
| `MCP_TRANSPORT_ERROR` | `MCPError` | MCP transport error (network, protocol) |
| `MCP_SERVER_ERROR` | `MCPError` | MCP server returned an error |
| `MCP_TIMEOUT` | `MCPTimeoutError` | MCP operation timed out |

### System Errors

| Error Code | Exception Class | When It Occurs |
|------------|----------------|----------------|
| `RESOURCE_EXHAUSTED` | `ToolProcessorError` | System resources exhausted (memory, threads) |
| `CONFIGURATION_ERROR` | `ToolProcessorError` | Invalid configuration |

---

## Error Handling Patterns

### Pattern 1: Catch Specific Errors

```python
from chuk_tool_processor.core.exceptions import (
    ToolNotFoundError,
    ToolTimeoutError,
    ToolCircuitOpenError,
)

try:
    results = await processor.process(llm_output)
except ToolNotFoundError as e:
    # Suggest available tools to LLM
    available = e.details.get("available_tools", [])
    print(f"Tool not found. Try one of: {available}")
except ToolTimeoutError as e:
    # Inform LLM to use faster alternative
    timeout = e.details["timeout"]
    print(f"Tool timed out after {timeout}s")
except ToolCircuitOpenError as e:
    # Tell LLM this service is temporarily down
    reset_time = e.details.get("reset_timeout")
    print(f"Service unavailable, retry in {reset_time}s")
```

### Pattern 2: Check Error Codes

```python
from chuk_tool_processor.core.exceptions import ErrorCode, ToolProcessorError

try:
    results = await processor.process(llm_output)
except ToolProcessorError as e:
    if e.code == ErrorCode.TOOL_NOT_FOUND:
        # Handle missing tool
        pass
    elif e.code == ErrorCode.TOOL_TIMEOUT:
        # Handle timeout
        pass
    elif e.code == ErrorCode.TOOL_RATE_LIMITED:
        # Handle rate limit
        retry_after = e.details.get("retry_after")
        print(f"Rate limited. Retry in {retry_after}s")
```

### Pattern 3: Serialize for Logging

```python
try:
    results = await processor.process(llm_output)
except ToolProcessorError as e:
    # Convert to dict for structured logging
    error_dict = e.to_dict()
    logger.error("Tool execution failed", extra=error_dict)

    # Example output:
    # {
    #   "error": "ToolCircuitOpenError",
    #   "code": "TOOL_CIRCUIT_OPEN",
    #   "message": "Tool 'api_tool' circuit breaker is open...",
    #   "details": {
    #     "tool_name": "api_tool",
    #     "failure_count": 5,
    #     "reset_timeout": 60.0
    #   }
    # }
```

### Pattern 4: Handle ToolExecutionResult Errors

```python
# process() returns results, not exceptions
results = await processor.process(llm_output)

for result in results:
    if result.error:
        # Error message is in result.error
        print(f"Tool '{result.tool}' failed: {result.error}")

        # Check if it was retried
        if result.attempts > 1:
            print(f"Failed after {result.attempts} attempts")
    else:
        print(f"Tool '{result.tool}' succeeded: {result.result}")
```

---

## ErrorInfo Model Reference

The `ErrorInfo` Pydantic model provides structured error information in `ToolResult`:

```python
from chuk_tool_processor.core.exceptions import ErrorInfo, ErrorCode, ErrorCategory

class ErrorInfo(BaseModel):
    """Structured error information for ToolResult."""

    code: ErrorCode          # Machine-readable error code
    category: ErrorCategory  # High-level category for decisions
    message: str             # Human-readable error message
    retryable: bool          # Whether error is generally retryable
    retry_after_ms: int | None  # Suggested retry delay (milliseconds)
    details: dict[str, Any]  # Additional context
```

### Creating ErrorInfo

```python
# From an exception
from chuk_tool_processor.core.exceptions import ErrorInfo, ToolCircuitOpenError

error = ToolCircuitOpenError("api_tool", failure_count=5, reset_timeout=30.0)
info = error.to_error_info()
# or
info = ErrorInfo.from_exception(error)

# From an error string (backwards compatibility)
info = ErrorInfo.from_error_string("Rate limit exceeded", tool_name="api_tool")
```

### Accessing in ToolResult

```python
result = await processor.process(calls)
for r in result:
    # Convenience properties
    if not r.is_success:
        print(f"Category: {r.error_category}")
        print(f"Code: {r.error_code}")
        print(f"Retryable: {r.retryable}")
        print(f"Retry after: {r.retry_after_ms}ms")

    # Full error_info access
    if r.error_info:
        print(f"Details: {r.error_info.details}")
        print(f"Full dump: {r.error_info.model_dump()}")
```

---

## Error Details Reference

Each error includes structured `details` for programmatic handling.

### ToolNotFoundError

```python
{
    "tool_name": "search",
    "available_tools": ["calculator", "weather", "database"]
}
```

### ToolTimeoutError

```python
{
    "tool_name": "slow_api",
    "timeout": 30.0,
    "attempts": 3
}
```

### ToolValidationError

```python
{
    "tool_name": "calculator",
    "validation_type": "arguments",  # or "result"
    "errors": {
        "operation": "field required",
        "a": "value is not a valid float"
    }
}
```

### ToolRateLimitedError

```python
{
    "tool_name": "api_tool",
    "retry_after": 45.2,  # seconds until retry allowed
    "limit": 100          # configured rate limit
}
```

### ToolCircuitOpenError

```python
{
    "tool_name": "failing_api",
    "failure_count": 5,
    "reset_timeout": 60.0  # seconds until circuit attempts recovery
}
```

### MCPConnectionError

```python
{
    "server_name": "notion",
    "reason": "Connection refused"
}
```

### MCPTimeoutError

```python
{
    "server_name": "sqlite",
    "operation": "tool_call",
    "timeout": 30.0
}
```

---

## Error Categories by Retryability

### Retryable Errors

These errors may succeed if retried:

- `TOOL_EXECUTION_FAILED` (if transient)
- `TOOL_TIMEOUT`
- `MCP_TIMEOUT`
- `MCP_TRANSPORT_ERROR`
- `RESOURCE_EXHAUSTED`

**Automatic retry behavior:**
```python
processor = ToolProcessor(
    enable_retries=True,
    max_retries=3,
    retry_delay=1.0,
    retry_backoff=2.0
)
```

### Non-Retryable Errors

These errors will not succeed if retried:

- `TOOL_NOT_FOUND`
- `TOOL_VALIDATION_ERROR`
- `TOOL_ARGUMENT_ERROR`
- `PARSER_ERROR`
- `PARSER_INVALID_FORMAT`
- `CONFIGURATION_ERROR`

### Rate-Limited Errors

Special case - retryable after delay:

- `TOOL_RATE_LIMITED`: Check `retry_after` in details
- `TOOL_CIRCUIT_OPEN`: Check `reset_timeout` in details

---

## Integration Examples

### Example 1: LLM Error Recovery

```python
async def call_tool_with_llm_recovery(processor, llm_output):
    """Call tool and provide LLM-friendly error messages."""
    try:
        results = await processor.process(llm_output)

        for result in results:
            if result.error:
                # Parse error to give LLM actionable feedback
                if "not found" in result.error.lower():
                    return {
                        "success": False,
                        "message": f"Tool '{result.tool}' doesn't exist. "
                                   f"Available tools: {list_available_tools()}"
                    }
                elif "rate limit" in result.error.lower():
                    return {
                        "success": False,
                        "message": "Rate limit exceeded. Try again in 1 minute."
                    }
                elif "timeout" in result.error.lower():
                    return {
                        "success": False,
                        "message": f"Tool took too long. Consider using a faster alternative."
                    }
            else:
                return {"success": True, "result": result.result}

    except ToolProcessorError as e:
        # Fallback for exceptions not caught by result.error
        return {"success": False, "message": str(e)}
```

### Example 2: Monitoring and Alerting

```python
import logging
from chuk_tool_processor.core.exceptions import ErrorCode, ToolProcessorError

logger = logging.getLogger(__name__)

async def process_with_monitoring(processor, llm_output):
    """Process with structured error logging for monitoring."""
    try:
        results = await processor.process(llm_output)

        for result in results:
            if result.error:
                # Log error for monitoring
                logger.warning(
                    "Tool execution failed",
                    extra={
                        "tool": result.tool,
                        "error": result.error,
                        "attempts": result.attempts,
                        "duration": result.duration
                    }
                )

        return results

    except ToolProcessorError as e:
        # Alert on critical errors
        error_dict = e.to_dict()

        if e.code in (ErrorCode.RESOURCE_EXHAUSTED, ErrorCode.MCP_CONNECTION_FAILED):
            logger.critical("Critical error", extra=error_dict)
            # Send alert to ops team
            send_alert(error_dict)
        else:
            logger.error("Tool processor error", extra=error_dict)

        raise
```

### Example 3: Testing Error Handling

```python
import pytest
from chuk_tool_processor.core.exceptions import ToolNotFoundError, ErrorCode

@pytest.mark.asyncio
async def test_tool_not_found_error():
    """Test handling of missing tool."""
    processor = ToolProcessor()

    with pytest.raises(ToolNotFoundError) as exc_info:
        await processor.process('<tool name="nonexistent" args="{}"/>')

    # Verify error code
    assert exc_info.value.code == ErrorCode.TOOL_NOT_FOUND

    # Verify error details
    assert exc_info.value.details["tool_name"] == "nonexistent"
    assert "available_tools" in exc_info.value.details

    # Verify serialization
    error_dict = exc_info.value.to_dict()
    assert error_dict["code"] == "TOOL_NOT_FOUND"
    assert error_dict["error"] == "ToolNotFoundError"
```

---

## Best Practices

### 1. Always Check result.error First

```python
results = await processor.process(llm_output)

# ✅ Good: Check error field
for result in results:
    if result.error:
        handle_error(result)
    else:
        use_result(result.result)

# ❌ Bad: Assume success
for result in results:
    use_result(result.result)  # Might be None!
```

### 2. Use Error Codes for Logic

```python
# ✅ Good: Use error codes
if e.code == ErrorCode.TOOL_RATE_LIMITED:
    retry_after = e.details.get("retry_after", 60)
    await asyncio.sleep(retry_after)

# ❌ Bad: Parse error messages
if "rate limit" in str(e):
    await asyncio.sleep(60)
```

### 3. Log Error Details

```python
# ✅ Good: Log structured details
logger.error("Tool failed", extra=e.to_dict())

# ❌ Bad: Log only message
logger.error(f"Tool failed: {e}")
```

### 4. Provide User-Friendly Messages

```python
# ✅ Good: Translate errors for users
try:
    results = await processor.process(llm_output)
except ToolTimeoutError:
    return "The operation took too long. Please try again."

# ❌ Bad: Show technical errors
try:
    results = await processor.process(llm_output)
except ToolTimeoutError as e:
    return f"ToolTimeoutError: {e.details}"
```

---

## See Also

- [README.md](../README.md) - Main documentation
- [CONFIGURATION.md](CONFIGURATION.md) - Configuration reference
- [examples/](../examples/) - Error handling examples
- [src/chuk_tool_processor/core/exceptions.py](../src/chuk_tool_processor/core/exceptions.py) - Error definitions
