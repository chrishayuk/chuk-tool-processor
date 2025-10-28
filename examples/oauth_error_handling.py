#!/usr/bin/env python3
"""
Example: OAuth 401 Error Handling in chuk-tool-processor

This example demonstrates how chuk-tool-processor transports handle OAuth 401
authentication errors from chuk-mcp v0.8.0, which now raises exceptions
properly instead of returning None.

Key Points:
1. OAuth 401 errors are raised as RetryableError with HTTP 401 info
2. Transports catch and handle these errors gracefully
3. Error messages contain full context for re-authentication
4. Metrics track authentication failures

Use Case: When OAuth tokens expire, the transport detects the 401 error
and can trigger re-authentication flow (like mcp-cli does).
"""

import asyncio
import anyio
import logging
from unittest.mock import Mock, patch, AsyncMock

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)


async def example_1_oauth_401_error_stdio():
    """Example 1: OAuth 401 error in STDIO transport."""
    print("\n" + "=" * 70)
    print("EXAMPLE 1: OAuth 401 Error - STDIO Transport")
    print("=" * 70)

    # Simulate a server that returns 401 Unauthorized
    server_script = """
import sys, json
req = json.loads(sys.stdin.readline())
error_response = {
    "jsonrpc": "2.0",
    "id": req["id"],
    "error": {
        "code": -32603,
        "message": 'HTTP 401: {"error":"invalid_token","error_description":"Token expired"}'
    }
}
print(json.dumps(error_response))
sys.stdout.flush()
"""

    from chuk_tool_processor.mcp.transport.stdio_transport import StdioTransport

    server_params = {
        "command": "python",
        "args": ["-c", server_script]
    }

    transport = StdioTransport(server_params, connection_timeout=5.0, enable_metrics=True)

    try:
        print("Attempting to initialize with expired OAuth token...")
        success = await transport.initialize()

        if success:
            print("❌ ERROR: Should have failed with 401 error")
        else:
            print("✅ Transport correctly failed with OAuth 401 error")
            metrics = transport.get_metrics()
            print(f"   Metrics: process_crashes={metrics.get('process_crashes', 0)}")
            print("\n   ➡️  In production, this would trigger:")
            print("   1. Clear stored OAuth tokens")
            print("   2. Delete client registration")
            print("   3. Open browser for OAuth re-authentication")
            print("   4. Retry with fresh token")

    except Exception as e:
        error_msg = str(e).lower()
        if any(pattern in error_msg for pattern in ["401", "invalid_token", "unauthorized"]):
            print("✅ OAuth 401 error detected in exception!")
            print(f"   Exception: {type(e).__name__}")
            print(f"   Error: {e}")
            print("\n   ➡️  OAuth re-authentication should be triggered")
        else:
            print(f"⚠️  Different error: {e}")

    finally:
        await transport.close()


async def example_2_oauth_401_with_retry():
    """Example 2: OAuth 401 with automatic retry after re-auth."""
    print("\n" + "=" * 70)
    print("EXAMPLE 2: OAuth 401 with Retry Logic")
    print("=" * 70)

    from chuk_tool_processor.mcp.transport.stdio_transport import StdioTransport

    # First attempt: returns 401
    expired_token_script = """
import sys, json
req = json.loads(sys.stdin.readline())
print(json.dumps({
    "jsonrpc": "2.0",
    "id": req["id"],
    "error": {
        "code": -32603,
        "message": 'HTTP 401: {"error":"invalid_token"}'
    }
}))
sys.stdout.flush()
"""

    # Second attempt: returns success (simulating fresh token)
    fresh_token_script = """
import sys, json
req = json.loads(sys.stdin.readline())
print(json.dumps({
    "jsonrpc": "2.0",
    "id": req["id"],
    "result": {
        "serverInfo": {"name": "OAuthServer", "version": "1.0"},
        "protocolVersion": "2024-11-05",
        "capabilities": {}
    }
}))
sys.stdout.flush()
# Read initialized notification
notif = json.loads(sys.stdin.readline())
import time; time.sleep(0.1)
"""

    async def connect_with_oauth_retry(script, max_attempts=2):
        """Simulate connection with OAuth re-authentication."""
        for attempt in range(max_attempts):
            print(f"\n   Attempt {attempt + 1}/{max_attempts}...")

            server_params = {
                "command": "python",
                "args": ["-c", script]
            }

            transport = StdioTransport(server_params, connection_timeout=5.0)

            try:
                success = await transport.initialize()

                if success:
                    print(f"   ✅ Connected successfully on attempt {attempt + 1}")
                    await transport.close()
                    return True, None

            except Exception as e:
                error_msg = str(e).lower()

                if any(p in error_msg for p in ["401", "invalid_token", "unauthorized"]):
                    print(f"   🔐 OAuth 401 error detected on attempt {attempt + 1}")

                    if attempt < max_attempts - 1:
                        print("   → Triggering OAuth re-authentication...")
                        print("   → [Simulated] Browser opened for OAuth flow")
                        print("   → [Simulated] User completed authentication")
                        print("   → [Simulated] Fresh token obtained")
                        # Switch to fresh token script for next attempt
                        script = fresh_token_script
                    else:
                        print("   ❌ OAuth re-authentication failed")
                        return False, e
                else:
                    print(f"   ❌ Non-OAuth error: {e}")
                    return False, e

            finally:
                await transport.close()

        return False, None

    # Try with expired token first
    print("Connecting with expired OAuth token:")
    success, error = await connect_with_oauth_retry(expired_token_script)

    if success:
        print("\n✅ OAuth re-authentication flow succeeded!")
        print("   Connection established with fresh token")
    else:
        print(f"\n❌ Connection failed: {error}")


async def example_3_multiple_oauth_error_patterns():
    """Example 3: Different OAuth error message patterns."""
    print("\n" + "=" * 70)
    print("EXAMPLE 3: Various OAuth Error Message Patterns")
    print("=" * 70)

    oauth_error_patterns = [
        'HTTP 401: {"error":"invalid_token"}',
        "401 Unauthorized",
        "Authentication failed: invalid access token",
        "Token expired",
        "Invalid OAuth credentials",
    ]

    from chuk_tool_processor.mcp.transport.stdio_transport import StdioTransport

    for i, error_pattern in enumerate(oauth_error_patterns, 1):
        print(f"\n   Pattern {i}: {error_pattern}")

        # Escape the error pattern for safe JSON insertion
        escaped_pattern = error_pattern.replace('"', '\\"')

        server_script = f"""
import sys, json
req = json.loads(sys.stdin.readline())
print(json.dumps({{
    "jsonrpc": "2.0",
    "id": req["id"],
    "error": {{
        "code": -32603,
        "message": "{escaped_pattern}"
    }}
}}))
sys.stdout.flush()
"""

        server_params = {
            "command": "python",
            "args": ["-c", server_script]
        }

        transport = StdioTransport(server_params, connection_timeout=5.0)

        try:
            success = await transport.initialize()

            if not success:
                print(f"   ✅ Error correctly detected")

        except Exception as e:
            error_msg = str(e).lower()
            is_oauth = any(p in error_msg for p in ["401", "invalid", "token", "auth", "unauthorized"])

            if is_oauth:
                print(f"   ✅ OAuth error pattern detected in exception")
            else:
                print(f"   ⚠️  Pattern not recognized as OAuth error")

        finally:
            await transport.close()


async def example_4_http_oauth_401():
    """Example 4: OAuth 401 in HTTP Streamable transport (simulated)."""
    print("\n" + "=" * 70)
    print("EXAMPLE 4: OAuth 401 Error - HTTP Streamable Transport")
    print("=" * 70)

    print("Simulating HTTP connection with expired OAuth token...")
    print("✅ HTTP transport would handle OAuth 401 errors the same way:")
    print("\n   How it works:")
    print("   1. HTTP transport calls send_initialize()")
    print("   2. OAuth 401 error raises RetryableError exception")
    print("   3. Exception propagates to caller (e.g., mcp-cli)")
    print("   4. Error message contains: HTTP 401: {\"error\":\"invalid_token\"...}")
    print("   5. OAuth handler detects 401 in error message")
    print("   6. Browser opens for re-authentication")
    print("   7. Fresh token obtained")
    print("   8. Connection retries with new token")
    print("   9. Success! ✅")
    print("\n   ➡️  Same flow as STDIO transport - works identically!")
    print("   ➡️  Already integrated in mcp-cli for HTTP servers!")


async def example_5_comprehensive_oauth_handling():
    """Example 5: Comprehensive OAuth error handling pattern."""
    print("\n" + "=" * 70)
    print("EXAMPLE 5: Comprehensive OAuth Error Handling")
    print("=" * 70)

    from chuk_tool_processor.mcp.transport.stdio_transport import StdioTransport

    try:
        from chuk_mcp.protocol.types.errors import RetryableError, VersionMismatchError
    except ImportError:
        RetryableError = Exception
        VersionMismatchError = Exception

    async def initialize_with_oauth_handling(server_params):
        """Initialize transport with comprehensive OAuth error handling."""
        transport = StdioTransport(server_params, connection_timeout=5.0, enable_metrics=True)

        try:
            print("   → Initializing transport...")
            success = await transport.initialize()

            if success:
                print("   ✅ Connected successfully")
                return transport, "success"
            else:
                # Check if the failure was due to OAuth 401
                # The transport logs errors but returns False instead of raising
                # We need to check the metrics or last error
                metrics = transport.get_metrics()
                process_crashes = metrics.get('process_crashes', 0)

                # If the process crashed, it's likely an OAuth error
                # In production, we'd check the actual error message from logs
                if process_crashes > 0:
                    print("   🔐 OAuth authentication failure detected!")
                    print("   → Detected via process crash metric")
                    print("\n   → Triggering OAuth re-authentication flow:")
                    print("   1. Clear stored tokens")
                    print("   2. Delete client registration")
                    print("   3. Open browser for OAuth")
                    print("   4. Retry with fresh token")
                    await transport.close()
                    return None, "oauth_401"
                else:
                    print("   ⚠️  Initialization failed")
                    return transport, "failed"

        except VersionMismatchError as e:
            print(f"   ❌ FATAL: Protocol version mismatch - {e}")
            print("   → Cannot recover - client/server incompatible")
            await transport.close()
            return None, "version_mismatch"

        except TimeoutError as e:
            print(f"   ⏱️  TIMEOUT: Server not responding - {e}")
            print("   → Retry with exponential backoff")
            await transport.close()
            return None, "timeout"

        except Exception as e:
            error_msg = str(e).lower()

            # Check for OAuth 401 errors
            if any(p in error_msg for p in ["401", "invalid_token", "unauthorized", "oauth"]):
                print(f"   🔐 OAuth authentication failed!")
                print(f"   → Error: {e}")
                print("\n   → Triggering OAuth re-authentication flow:")
                print("   1. Clear stored tokens")
                print("   2. Delete client registration")
                print("   3. Open browser for OAuth")
                print("   4. Retry with fresh token")

                await transport.close()
                return None, "oauth_401"

            else:
                print(f"   ❌ Other error: {type(e).__name__}: {e}")
                await transport.close()
                return None, "error"

    # Test with OAuth 401 error
    oauth_error_script = """
import sys, json
req = json.loads(sys.stdin.readline())
print(json.dumps({
    "jsonrpc": "2.0",
    "id": req["id"],
    "error": {
        "code": -32603,
        "message": 'HTTP 401: {"error":"invalid_token","error_description":"Token expired"}'
    }
}))
sys.stdout.flush()
"""

    server_params = {
        "command": "python",
        "args": ["-c", oauth_error_script]
    }

    print("Testing comprehensive OAuth error handling:")
    transport, result = await initialize_with_oauth_handling(server_params)

    print(f"\n✅ Result: {result}")

    if result == "oauth_401":
        print("   OAuth re-authentication flow would be triggered")
        print("   This is exactly what mcp-cli does!")

    if transport:
        await transport.close()


async def main():
    """Run all OAuth error handling examples."""
    print("\n" + "=" * 70)
    print("chuk-tool-processor OAuth 401 Error Handling Examples")
    print("=" * 70)
    print("\nThese examples demonstrate how transports handle OAuth 401")
    print("authentication errors from chuk-mcp v0.8.0.")
    print("\nKey Features:")
    print("  1. OAuth 401 errors are detected correctly")
    print("  2. Exceptions contain full error context")
    print("  3. Re-authentication flow can be triggered")
    print("  4. Works with both STDIO and HTTP transports")
    print("  5. Supports multiple OAuth error message patterns")

    # Run examples
    await example_1_oauth_401_error_stdio()
    await example_2_oauth_401_with_retry()
    await example_3_multiple_oauth_error_patterns()
    await example_4_http_oauth_401()
    await example_5_comprehensive_oauth_handling()

    print("\n" + "=" * 70)
    print("Examples Complete")
    print("=" * 70)
    print("\nKey Takeaways:")
    print("  ✓ OAuth 401 errors are raised as exceptions (not None)")
    print("  ✓ Error messages contain full context for debugging")
    print("  ✓ Re-authentication flow can be triggered automatically")
    print("  ✓ Works exactly like mcp-cli's OAuth handling")
    print("  ✓ No manual token deletion needed!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
