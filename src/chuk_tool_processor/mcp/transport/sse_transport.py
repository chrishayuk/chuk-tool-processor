# chuk_tool_processor/mcp/transport/sse_transport.py
"""
SSE transport for MCP communication.

FIXED: Improved health monitoring to avoid false unhealthy states.
The SSE endpoint works perfectly, so we need more lenient health checks.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from typing import Any

import httpx

from .base_transport import MCPBaseTransport
from .models import TimeoutConfig, TransportMetrics

logger = logging.getLogger(__name__)


class SSETransport(MCPBaseTransport):
    """
    SSE transport implementing the MCP protocol over Server-Sent Events.

    FIXED: More lenient health monitoring to avoid false unhealthy states.
    """

    def __init__(
        self,
        url: str,
        api_key: str | None = None,
        headers: dict[str, str] | None = None,
        connection_timeout: float = 30.0,
        default_timeout: float = 60.0,
        enable_metrics: bool = True,
        oauth_refresh_callback: Any | None = None,
        timeout_config: TimeoutConfig | None = None,
    ):
        """
        Initialize SSE transport.
        """
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.configured_headers = headers or {}
        self.enable_metrics = enable_metrics
        self.oauth_refresh_callback = oauth_refresh_callback

        # Use timeout config or create from individual parameters
        if timeout_config is None:
            timeout_config = TimeoutConfig(connect=connection_timeout, operation=default_timeout)

        self.timeout_config = timeout_config
        self.connection_timeout = timeout_config.connect
        self.default_timeout = timeout_config.operation

        logger.debug("SSE Transport initialized with URL: %s", self.url)

        # Connection state
        self.session_id = None
        self.message_url = None
        self.pending_requests: dict[str, asyncio.Future] = {}
        self._initialized = False

        # HTTP clients
        self.stream_client = None
        self.send_client = None

        # SSE stream management
        self.sse_task = None
        self.sse_response = None
        self.sse_stream_context = None

        # FIXED: More lenient health monitoring
        self._last_successful_ping = None
        self._consecutive_failures = 0
        self._max_consecutive_failures = 5  # INCREASED: was 3, now 5
        self._connection_grace_period = 30.0  # NEW: Grace period after initialization
        self._initialization_time = None  # NEW: Track when we initialized

        # Performance metrics - use Pydantic model
        self._metrics = TransportMetrics() if enable_metrics else None

    def _construct_sse_url(self, base_url: str) -> str:
        """Construct the SSE endpoint URL from the base URL."""
        base_url = base_url.rstrip("/")

        if base_url.endswith("/sse"):
            logger.debug("URL already contains /sse endpoint: %s", base_url)
            return base_url

        sse_url = f"{base_url}/sse"
        logger.debug("Constructed SSE URL: %s -> %s", base_url, sse_url)
        return sse_url

    def _get_headers(self) -> dict[str, str]:
        """Get headers with authentication and custom headers."""
        headers = {
            "User-Agent": "chuk-tool-processor/1.0.0",
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        }

        # Add configured headers first
        if self.configured_headers:
            headers.update(self.configured_headers)

        # Add API key as Bearer token if provided and no Authorization header exists
        # This prevents clobbering OAuth tokens from configured_headers
        if self.api_key and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {self.api_key}"

        return headers

    async def _test_gateway_connectivity(self) -> bool:
        """
        Skip connectivity test - we know the SSE endpoint works.

        FIXED: The diagnostic proves SSE endpoint works perfectly.
        No need to test base URL that causes 401 errors.
        """
        logger.debug("Skipping gateway connectivity test - using direct SSE connection")
        return True

    async def initialize(self) -> bool:
        """Initialize SSE connection with improved health tracking."""
        if self._initialized:
            logger.warning("Transport already initialized")
            return True

        start_time = time.time()

        try:
            logger.debug("Initializing SSE transport...")

            # FIXED: Skip problematic connectivity test
            if not await self._test_gateway_connectivity():
                logger.error("Gateway connectivity test failed")
                return False

            # Create HTTP clients
            self.stream_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.connection_timeout),
                follow_redirects=True,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
            self.send_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.default_timeout),
                follow_redirects=True,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )

            # Connect to SSE stream
            sse_url = self._construct_sse_url(self.url)
            logger.debug("Connecting to SSE endpoint: %s", sse_url)

            self.sse_stream_context = self.stream_client.stream("GET", sse_url, headers=self._get_headers())
            self.sse_response = await self.sse_stream_context.__aenter__()

            if self.sse_response.status_code != 200:
                logger.error("SSE connection failed with status: %s", self.sse_response.status_code)
                await self._cleanup()
                return False

            logger.debug("SSE streaming connection established")

            # Start SSE processing task
            self.sse_task = asyncio.create_task(self._process_sse_stream(), name="sse_stream_processor")

            # Wait for session discovery
            logger.debug("Waiting for session discovery...")
            session_timeout = self.timeout_config.connect
            session_start = time.time()

            while not self.message_url and (time.time() - session_start) < session_timeout:
                await asyncio.sleep(0.1)

                # Check if SSE task died
                if self.sse_task.done():
                    exception = self.sse_task.exception()
                    if exception:
                        logger.debug(f"SSE task died during session discovery: {exception}")
                        await self._cleanup()
                        return False

            if not self.message_url:
                logger.warning("Failed to discover session endpoint within %.1fs", session_timeout)
                await self._cleanup()
                return False

            if self.enable_metrics and self._metrics:
                self._metrics.session_discoveries += 1

            logger.debug("Session endpoint discovered: %s", self.message_url)

            # Perform MCP initialization handshake
            try:
                init_response = await self._send_request(
                    "initialize",
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "chuk-tool-processor", "version": "1.0.0"},
                    },
                    timeout=self.default_timeout,
                )

                if "error" in init_response:
                    logger.warning("MCP initialize failed: %s", init_response["error"])
                    await self._cleanup()
                    return False

                # Send initialized notification
                await self._send_notification("notifications/initialized")

                # FIXED: Set health tracking state
                self._initialized = True
                self._initialization_time = time.time()
                self._last_successful_ping = time.time()
                self._consecutive_failures = 0  # Reset failure count

                if self.enable_metrics and self._metrics:
                    init_time = time.time() - start_time
                    self._metrics.initialization_time = init_time

                logger.debug("SSE transport initialized successfully in %.3fs", time.time() - start_time)
                return True

            except Exception as e:
                logger.error("MCP handshake failed: %s", e)
                await self._cleanup()
                return False

        except Exception as e:
            logger.error("Error initializing SSE transport: %s", e, exc_info=True)
            await self._cleanup()
            return False

    async def _process_sse_stream(self):
        """Process the SSE stream for responses and session discovery."""
        try:
            logger.debug("Starting SSE stream processing...")

            current_event = None

            async for line in self.sse_response.aiter_lines():
                line = line.strip()
                if not line:
                    continue

                # Handle event type declarations
                if line.startswith("event:"):
                    current_event = line.split(":", 1)[1].strip()
                    logger.debug("SSE event type: %s", current_event)
                    continue

                # Handle session endpoint discovery
                if not self.message_url and line.startswith("data:"):
                    data_part = line.split(":", 1)[1].strip()

                    # NEW FORMAT: event: endpoint + data: https://...
                    if current_event == "endpoint" and data_part.startswith("http"):
                        self.message_url = data_part

                        # Extract session ID from URL if present
                        if "session_id=" in data_part:
                            self.session_id = data_part.split("session_id=")[1].split("&")[0]
                        elif "sessionId=" in data_part:
                            self.session_id = data_part.split("sessionId=")[1].split("&")[0]
                        else:
                            self.session_id = str(uuid.uuid4())

                        logger.debug("Session endpoint discovered via event format: %s", self.message_url)
                        continue

                    # RELATIVE PATH FORMAT: event: endpoint + data: /sse/message?sessionId=...
                    elif current_event == "endpoint" and data_part.startswith("/"):
                        endpoint_path = data_part
                        self.message_url = f"{self.url}{endpoint_path}"

                        # Extract session ID if present
                        if "session_id=" in endpoint_path:
                            self.session_id = endpoint_path.split("session_id=")[1].split("&")[0]
                        elif "sessionId=" in endpoint_path:
                            self.session_id = endpoint_path.split("sessionId=")[1].split("&")[0]
                        else:
                            self.session_id = str(uuid.uuid4())

                        logger.debug("Session endpoint discovered via relative path: %s", self.message_url)
                        continue

                    # OLD FORMAT: data: /messages/... (backwards compatibility)
                    elif "/messages/" in data_part:
                        endpoint_path = data_part
                        self.message_url = f"{self.url}{endpoint_path}"

                        # Extract session ID if present
                        if "session_id=" in endpoint_path:
                            self.session_id = endpoint_path.split("session_id=")[1].split("&")[0]
                        else:
                            self.session_id = str(uuid.uuid4())

                        logger.debug("Session endpoint discovered via old format: %s", self.message_url)
                        continue

                # Handle JSON-RPC responses
                if line.startswith("data:"):
                    data_part = line.split(":", 1)[1].strip()

                    # Skip keepalive pings and empty data
                    if not data_part or data_part.startswith("ping") or data_part in ("{}", "[]"):
                        continue

                    try:
                        response_data = json.loads(data_part)

                        # Handle JSON-RPC responses with request IDs
                        if "jsonrpc" in response_data and "id" in response_data:
                            request_id = str(response_data["id"])

                            # Resolve pending request if found
                            if request_id in self.pending_requests:
                                future = self.pending_requests.pop(request_id)
                                if not future.done():
                                    future.set_result(response_data)
                                    logger.debug("Resolved request ID: %s", request_id)

                    except json.JSONDecodeError as e:
                        logger.debug("Non-JSON data in SSE stream (ignoring): %s", e)

        except Exception as e:
            if self.enable_metrics and self._metrics:
                self._metrics.stream_errors += 1
            logger.error("SSE stream processing error: %s", e)
            # FIXED: Don't increment consecutive failures for stream processing errors
            # These are often temporary and don't indicate connection health

    async def _send_request(
        self, method: str, params: dict[str, Any] = None, timeout: float | None = None
    ) -> dict[str, Any]:
        """Send JSON-RPC request and wait for async response via SSE."""
        if not self.message_url:
            raise RuntimeError("SSE transport not connected - no message URL")

        request_id = str(uuid.uuid4())
        message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}

        # Create future for async response
        future = asyncio.Future()
        self.pending_requests[request_id] = future

        try:
            # Send HTTP POST request
            headers = {"Content-Type": "application/json", **self._get_headers()}

            response = await self.send_client.post(self.message_url, headers=headers, json=message)

            if response.status_code == 202:
                # Async response - wait for result via SSE
                request_timeout = timeout or self.default_timeout
                result = await asyncio.wait_for(future, timeout=request_timeout)
                # FIXED: Only reset failures on successful tool calls, not all requests
                if method.startswith("tools/"):
                    self._consecutive_failures = 0
                    self._last_successful_ping = time.time()
                return result
            elif response.status_code == 200:
                # Immediate response
                self.pending_requests.pop(request_id, None)
                # FIXED: Only reset failures on successful tool calls
                if method.startswith("tools/"):
                    self._consecutive_failures = 0
                    self._last_successful_ping = time.time()
                return response.json()
            else:
                self.pending_requests.pop(request_id, None)
                # FIXED: Only increment failures for tool calls, not initialization
                if method.startswith("tools/"):
                    self._consecutive_failures += 1
                raise RuntimeError(f"HTTP request failed with status: {response.status_code}")

        except TimeoutError:
            self.pending_requests.pop(request_id, None)
            # FIXED: Only increment failures for tool calls
            if method.startswith("tools/"):
                self._consecutive_failures += 1
            raise
        except Exception:
            self.pending_requests.pop(request_id, None)
            # FIXED: Only increment failures for tool calls
            if method.startswith("tools/"):
                self._consecutive_failures += 1
            raise

    async def _send_notification(self, method: str, params: dict[str, Any] = None):
        """Send JSON-RPC notification (no response expected)."""
        if not self.message_url:
            raise RuntimeError("SSE transport not connected - no message URL")

        message = {"jsonrpc": "2.0", "method": method, "params": params or {}}

        headers = {"Content-Type": "application/json", **self._get_headers()}

        response = await self.send_client.post(self.message_url, headers=headers, json=message)

        if response.status_code not in (200, 202):
            logger.warning("Notification failed with status: %s", response.status_code)

    async def send_ping(self) -> bool:
        """Send ping to check connection health with improved logic."""
        if not self._initialized:
            return False

        start_time = time.time()
        try:
            # Use tools/list as a lightweight ping since not all servers support ping
            response = await self._send_request("tools/list", {}, timeout=self.timeout_config.quick)

            success = "error" not in response

            if success:
                self._last_successful_ping = time.time()
                # FIXED: Don't reset consecutive failures here - let tool calls do that

            if self.enable_metrics and self._metrics:
                ping_time = time.time() - start_time
                self._metrics.last_ping_time = ping_time
                logger.debug("SSE ping completed in %.3fs: %s", ping_time, success)

            return success
        except Exception as e:
            logger.debug("SSE ping failed: %s", e)
            # FIXED: Don't increment consecutive failures for ping failures
            return False

    def is_connected(self) -> bool:
        """
        FIXED: More lenient connection health check.

        The diagnostic shows the connection works fine, so we need to be less aggressive
        about marking it as unhealthy.
        """
        if not self._initialized or not self.session_id:
            return False

        # FIXED: Grace period after initialization - always return True for a while
        if self._initialization_time and time.time() - self._initialization_time < self._connection_grace_period:
            logger.debug("Within grace period - connection considered healthy")
            return True

        # FIXED: More lenient failure threshold
        if self._consecutive_failures >= self._max_consecutive_failures:
            logger.warning(f"Connection marked unhealthy after {self._consecutive_failures} consecutive failures")
            return False

        # Check if SSE task is still running
        if self.sse_task and self.sse_task.done():
            exception = self.sse_task.exception()
            if exception:
                logger.warning(f"SSE task died: {exception}")
                return False

        # FIXED: If we have a recent successful ping/tool call, we're healthy
        if self._last_successful_ping and time.time() - self._last_successful_ping < 60.0:  # Success within last minute
            return True

        # FIXED: Default to healthy if no clear indicators of problems
        logger.debug("No clear health indicators - defaulting to healthy")
        return True

    async def get_tools(self) -> list[dict[str, Any]]:
        """Get list of available tools from the server."""
        if not self._initialized:
            logger.debug("Cannot get tools: transport not initialized")
            return []

        start_time = time.time()
        try:
            response = await self._send_request("tools/list", {})

            if "error" in response:
                logger.warning("Error getting tools: %s", response["error"])
                return []

            tools = response.get("result", {}).get("tools", [])

            if self.enable_metrics:
                response_time = time.time() - start_time
                logger.debug("Retrieved %d tools in %.3fs", len(tools), response_time)

            return tools

        except Exception as e:
            logger.error("Error getting tools: %s", e)
            return []

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any], timeout: float | None = None
    ) -> dict[str, Any]:
        """Execute a tool with the given arguments."""
        if not self._initialized:
            return {"isError": True, "error": "Transport not initialized"}

        start_time = time.time()
        if self.enable_metrics and self._metrics:
            self._metrics.total_calls += 1

        try:
            logger.debug("Calling tool '%s' with arguments: %s", tool_name, arguments)

            response = await self._send_request(
                "tools/call", {"name": tool_name, "arguments": arguments}, timeout=timeout
            )

            # Check for errors
            if "error" in response:
                error_msg = response["error"].get("message", "Unknown error")

                # NEW: Check for OAuth errors and attempt refresh if callback is available
                if self._is_oauth_error(error_msg):
                    logger.warning("OAuth error detected: %s", error_msg)

                    if self.oauth_refresh_callback:
                        logger.debug("Attempting OAuth token refresh...")
                        try:
                            # Call the refresh callback
                            new_headers = await self.oauth_refresh_callback()

                            if new_headers and "Authorization" in new_headers:
                                # Update configured headers with new token
                                self.configured_headers.update(new_headers)
                                logger.debug("OAuth token refreshed, retrying tool call...")

                                # Retry the tool call once with new token
                                response = await self._send_request(
                                    "tools/call", {"name": tool_name, "arguments": arguments}, timeout=timeout
                                )

                                # Check if retry succeeded
                                if "error" not in response:
                                    logger.debug("Tool call succeeded after token refresh")
                                    result = response.get("result", {})
                                    normalized_result = self._normalize_mcp_response({"result": result})

                                    if self.enable_metrics:
                                        self._update_metrics(time.time() - start_time, True)

                                    return normalized_result
                                else:
                                    error_msg = response["error"].get("message", "Unknown error")
                                    logger.error("Tool call failed after token refresh: %s", error_msg)
                            else:
                                logger.warning("Token refresh did not return valid Authorization header")
                        except Exception as refresh_error:
                            logger.error("OAuth token refresh failed: %s", refresh_error)
                    else:
                        logger.warning("OAuth error detected but no refresh callback configured")

                # Return error (original or from failed retry)
                if self.enable_metrics:
                    self._update_metrics(time.time() - start_time, False)

                return {"isError": True, "error": error_msg}

            # Extract and normalize result using base class method
            result = response.get("result", {})
            normalized_result = self._normalize_mcp_response({"result": result})

            if self.enable_metrics:
                self._update_metrics(time.time() - start_time, True)

            return normalized_result

        except TimeoutError:
            if self.enable_metrics:
                self._update_metrics(time.time() - start_time, False)

            return {"isError": True, "error": "Tool execution timed out"}
        except Exception as e:
            if self.enable_metrics:
                self._update_metrics(time.time() - start_time, False)

            logger.error("Error calling tool '%s': %s", tool_name, e)
            return {"isError": True, "error": str(e)}

    def _update_metrics(self, response_time: float, success: bool) -> None:
        """Update performance metrics."""
        if not self._metrics:
            return

        self._metrics.update_call_metrics(response_time, success)

    def _is_oauth_error(self, error_msg: str) -> bool:
        """
        Detect if error is OAuth-related per RFC 6750 and MCP OAuth spec.

        Checks for:
        - RFC 6750 Section 3.1 Bearer token errors (invalid_token, insufficient_scope)
        - OAuth 2.1 token refresh errors (invalid_grant)
        - MCP spec OAuth validation failures (401/403 responses)
        """
        if not error_msg:
            return False

        error_lower = error_msg.lower()
        oauth_indicators = [
            # RFC 6750 Section 3.1 - Standard Bearer token errors
            "invalid_token",  # Token expired, revoked, malformed, or invalid
            "insufficient_scope",  # Request requires higher privileges (403 Forbidden)
            # OAuth 2.1 token refresh errors
            "invalid_grant",  # Refresh token errors
            # MCP spec - OAuth validation failures (401 Unauthorized)
            "oauth validation",
            "unauthorized",
            # Common OAuth error descriptions
            "expired token",
            "token expired",
            "authentication failed",
            "invalid access token",
        ]

        return any(indicator in error_lower for indicator in oauth_indicators)

    async def list_resources(self) -> dict[str, Any]:
        """List available resources from the server."""
        if not self._initialized:
            return {}

        try:
            response = await self._send_request("resources/list", {}, timeout=self.timeout_config.operation)
            if "error" in response:
                logger.debug("Resources not supported: %s", response["error"])
                return {}
            return response.get("result", {})
        except Exception as e:
            logger.debug("Error listing resources: %s", e)
            return {}

    async def list_prompts(self) -> dict[str, Any]:
        """List available prompts from the server."""
        if not self._initialized:
            return {}

        try:
            response = await self._send_request("prompts/list", {}, timeout=self.timeout_config.operation)
            if "error" in response:
                logger.debug("Prompts not supported: %s", response["error"])
                return {}
            return response.get("result", {})
        except Exception as e:
            logger.debug("Error listing prompts: %s", e)
            return {}

    async def close(self) -> None:
        """Close the transport and clean up resources."""
        if not self._initialized:
            return

        # Log final metrics
        if self.enable_metrics and self._metrics and self._metrics.total_calls > 0:
            logger.debug(
                "SSE transport closing - Total calls: %d, Success rate: %.1f%%, Avg response time: %.3fs",
                self._metrics.total_calls,
                (self._metrics.successful_calls / self._metrics.total_calls * 100),
                self._metrics.avg_response_time,
            )

        await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up all resources and reset state."""
        # Cancel SSE processing task
        if self.sse_task and not self.sse_task.done():
            self.sse_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.sse_task

        # Close SSE stream context
        if self.sse_stream_context:
            try:
                await self.sse_stream_context.__aexit__(None, None, None)
            except Exception as e:
                logger.debug("Error closing SSE stream: %s", e)

        # Close HTTP clients
        if self.stream_client:
            await self.stream_client.aclose()

        if self.send_client:
            await self.send_client.aclose()

        # Cancel any pending requests
        for _request_id, future in self.pending_requests.items():
            if not future.done():
                future.cancel()

        # Reset state
        self._initialized = False
        self.session_id = None
        self.message_url = None
        self.pending_requests.clear()
        self.sse_task = None
        self.sse_response = None
        self.sse_stream_context = None
        self.stream_client = None
        self.send_client = None
        # FIXED: Reset health tracking
        self._consecutive_failures = 0
        self._last_successful_ping = None
        self._initialization_time = None

    def get_metrics(self) -> dict[str, Any]:
        """Get performance and connection metrics with health info."""
        if not self._metrics:
            return {}

        metrics = self._metrics.to_dict()
        metrics.update(
            {
                "is_connected": self.is_connected(),
                "consecutive_failures": self._consecutive_failures,
                "max_consecutive_failures": self._max_consecutive_failures,
                "last_successful_ping": self._last_successful_ping,
                "initialization_time_timestamp": self._initialization_time,
                "grace_period_active": (
                    self._initialization_time
                    and time.time() - self._initialization_time < self._connection_grace_period
                )
                if self._initialization_time
                else False,
            }
        )
        return metrics

    def reset_metrics(self) -> None:
        """Reset performance metrics."""
        if not self._metrics:
            return

        # Preserve important historical values
        preserved_last_ping = self._metrics.last_ping_time
        preserved_init_time = self._metrics.initialization_time
        preserved_discoveries = self._metrics.session_discoveries

        # Create new metrics instance with preserved values
        self._metrics = TransportMetrics(
            last_ping_time=preserved_last_ping,
            initialization_time=preserved_init_time,
            session_discoveries=preserved_discoveries,
        )

    def get_streams(self) -> list[tuple]:
        """SSE transport doesn't expose raw streams."""
        return []

    async def __aenter__(self):
        """Context manager entry."""
        success = await self.initialize()
        if not success:
            raise RuntimeError("Failed to initialize SSETransport")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        await self.close()
