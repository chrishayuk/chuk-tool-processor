# chuk_tool_processor/mcp/transport/http_streamable_transport.py - ENHANCED
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from chuk_mcp.protocol.messages import (  # type: ignore[import-untyped]
    send_initialize,
    send_ping,
    send_prompts_get,
    send_prompts_list,
    send_resources_list,
    send_resources_read,
    send_tools_call,
    send_tools_list,
)

# Import chuk-mcp HTTP transport components
from chuk_mcp.transports.http import http_client  # type: ignore[import-untyped]
from chuk_mcp.transports.http.parameters import StreamableHTTPParameters  # type: ignore[import-untyped]

from .base_transport import MCPBaseTransport

logger = logging.getLogger(__name__)


class HTTPStreamableTransport(MCPBaseTransport):
    """
    HTTP Streamable transport using chuk-mcp HTTP client.

    ENHANCED: Now matches SSE transport robustness with improved connection
    management, health monitoring, and comprehensive error handling.
    """

    def __init__(
        self,
        url: str,
        api_key: str | None = None,
        headers: dict[str, str] | None = None,  # NEW: Headers support
        connection_timeout: float = 30.0,
        default_timeout: float = 30.0,
        session_id: str | None = None,
        enable_metrics: bool = True,
    ):
        """
        Initialize HTTP Streamable transport with enhanced configuration.

        Args:
            url: HTTP server URL (should end with /mcp)
            api_key: Optional API key for authentication
            headers: Optional custom headers (NEW)
            connection_timeout: Timeout for initial connection
            default_timeout: Default timeout for operations
            session_id: Optional session ID for stateful connections
            enable_metrics: Whether to track performance metrics
        """
        # Ensure URL points to the /mcp endpoint
        if not url.endswith("/mcp"):
            self.url = f"{url.rstrip('/')}/mcp"
        else:
            self.url = url

        self.api_key = api_key
        self.configured_headers = headers or {}  # NEW: Store configured headers
        self.connection_timeout = connection_timeout
        self.default_timeout = default_timeout
        self.session_id = session_id
        self.enable_metrics = enable_metrics

        logger.debug("HTTP Streamable transport initialized with URL: %s", self.url)
        if self.api_key:
            logger.debug("API key configured for authentication")
        if self.configured_headers:
            logger.debug("Custom headers configured: %s", list(self.configured_headers.keys()))
        if self.session_id:
            logger.debug("Session ID configured: %s", self.session_id)

        # State tracking (enhanced like SSE)
        self._http_context = None
        self._read_stream = None
        self._write_stream = None
        self._initialized = False

        # Health monitoring (NEW - like SSE)
        self._last_successful_ping = None
        self._consecutive_failures = 0
        self._max_consecutive_failures = 3

        # Performance metrics (enhanced like SSE)
        self._metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_time": 0.0,
            "avg_response_time": 0.0,
            "last_ping_time": None,
            "initialization_time": None,
            "connection_resets": 0,
            "stream_errors": 0,
            "connection_errors": 0,  # NEW
            "recovery_attempts": 0,  # NEW
        }

    def _get_headers(self) -> dict[str, str]:
        """Get headers with authentication and custom headers (like SSE)."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "chuk-tool-processor/1.0.0",
        }

        # Add configured headers first
        if self.configured_headers:
            headers.update(self.configured_headers)

        # Add API key as Bearer token if provided
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # Add session ID if provided
        if self.session_id:
            headers["X-Session-ID"] = self.session_id

        return headers

    async def _test_connection_health(self) -> bool:
        """Test basic HTTP connectivity (like SSE's connectivity test)."""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                # Test basic connectivity to base URL
                base_url = self.url.replace("/mcp", "")
                response = await client.get(f"{base_url}/health", headers=self._get_headers())
                logger.debug("Health check response: %s", response.status_code)
                return response.status_code < 500  # Accept any non-server-error
        except Exception as e:
            logger.debug("Connection health test failed: %s", e)
            return True  # Don't fail on health check errors

    async def initialize(self) -> bool:
        """Initialize with enhanced error handling and health monitoring."""
        if self._initialized:
            logger.warning("Transport already initialized")
            return True

        start_time = time.time()

        try:
            logger.debug("Initializing HTTP Streamable transport to %s", self.url)

            # Test basic connectivity first (like SSE)
            if not await self._test_connection_health():
                logger.warning("Connection health test failed, proceeding anyway")

            # Build headers properly
            headers = self._get_headers()
            logger.debug("Using headers: %s", list(headers.keys()))

            # Create StreamableHTTPParameters with proper configuration
            http_params = StreamableHTTPParameters(
                url=self.url,
                timeout=self.default_timeout,
                headers=headers,
                bearer_token=None,  # Don't duplicate auth - it's in headers
                session_id=self.session_id,
                enable_streaming=True,
                max_concurrent_requests=5,
                max_retries=2,
                retry_delay=1.0,
                user_agent="chuk-tool-processor/1.0.0",
            )

            # Create and enter the HTTP context
            self._http_context = http_client(http_params)

            logger.debug("Establishing HTTP connection...")
            self._read_stream, self._write_stream = await asyncio.wait_for(
                self._http_context.__aenter__(), timeout=self.connection_timeout
            )

            # Enhanced MCP initialize sequence
            logger.debug("Sending MCP initialize request...")
            init_start = time.time()

            await asyncio.wait_for(send_initialize(self._read_stream, self._write_stream), timeout=self.default_timeout)

            init_time = time.time() - init_start
            logger.debug("MCP initialize completed in %.3fs", init_time)

            # Verify connection with ping (enhanced like SSE)
            logger.debug("Verifying connection with ping...")
            ping_start = time.time()
            ping_success = await asyncio.wait_for(
                send_ping(self._read_stream, self._write_stream),
                timeout=10.0,  # Longer timeout for initial ping
            )
            ping_time = time.time() - ping_start

            if ping_success:
                self._initialized = True
                self._last_successful_ping = time.time()
                self._consecutive_failures = 0

                total_init_time = time.time() - start_time
                if self.enable_metrics:
                    self._metrics["initialization_time"] = total_init_time
                    self._metrics["last_ping_time"] = ping_time

                logger.debug(
                    "HTTP Streamable transport initialized successfully in %.3fs (ping: %.3fs)",
                    total_init_time,
                    ping_time,
                )
                return True
            else:
                logger.warning("HTTP connection established but ping failed")
                # Still consider it initialized since connection was established
                self._initialized = True
                self._consecutive_failures = 1  # Mark one failure
                if self.enable_metrics:
                    self._metrics["initialization_time"] = time.time() - start_time
                return True

        except TimeoutError:
            logger.error("HTTP Streamable initialization timed out after %ss", self.connection_timeout)
            await self._cleanup()
            if self.enable_metrics:
                self._metrics["connection_errors"] += 1
            return False
        except Exception as e:
            logger.error("Error initializing HTTP Streamable transport: %s", e, exc_info=True)
            await self._cleanup()
            if self.enable_metrics:
                self._metrics["connection_errors"] += 1
            return False

    async def _attempt_recovery(self) -> bool:
        """Attempt to recover from connection issues (NEW - like SSE resilience)."""
        if self.enable_metrics:
            self._metrics["recovery_attempts"] += 1

        logger.debug("Attempting HTTP connection recovery...")

        try:
            # Clean up existing connection
            await self._cleanup()

            # Re-initialize
            return await self.initialize()
        except Exception as e:
            logger.warning("Recovery attempt failed: %s", e)
            return False

    async def close(self) -> None:
        """Close with enhanced cleanup and metrics reporting."""
        if not self._initialized:
            return

        # Enhanced metrics logging (like SSE)
        if self.enable_metrics and self._metrics["total_calls"] > 0:
            success_rate = self._metrics["successful_calls"] / self._metrics["total_calls"] * 100
            logger.debug(
                "HTTP Streamable transport closing - Calls: %d, Success: %.1f%%, "
                "Avg time: %.3fs, Recoveries: %d, Errors: %d",
                self._metrics["total_calls"],
                success_rate,
                self._metrics["avg_response_time"],
                self._metrics["recovery_attempts"],
                self._metrics["connection_errors"],
            )

        try:
            if self._http_context is not None:
                await self._http_context.__aexit__(None, None, None)
                logger.debug("HTTP Streamable context closed")

        except Exception as e:
            logger.debug("Error during transport close: %s", e)
        finally:
            await self._cleanup()

    async def _cleanup(self) -> None:
        """Enhanced cleanup with state reset."""
        self._http_context = None
        self._read_stream = None
        self._write_stream = None
        self._initialized = False

    async def send_ping(self) -> bool:
        """Enhanced ping with health monitoring (like SSE)."""
        if not self._initialized or not self._read_stream:
            logger.error("Cannot send ping: transport not initialized")
            return False

        start_time = time.time()
        try:
            result = await asyncio.wait_for(
                send_ping(self._read_stream, self._write_stream), timeout=self.default_timeout
            )

            success = bool(result)

            if success:
                self._last_successful_ping = time.time()
                self._consecutive_failures = 0
            else:
                self._consecutive_failures += 1

            if self.enable_metrics:
                ping_time = time.time() - start_time
                self._metrics["last_ping_time"] = ping_time
                logger.debug("HTTP Streamable ping completed in %.3fs: %s", ping_time, success)

            return success
        except TimeoutError:
            logger.error("HTTP Streamable ping timed out")
            self._consecutive_failures += 1
            return False
        except Exception as e:
            logger.error("HTTP Streamable ping failed: %s", e)
            self._consecutive_failures += 1
            if self.enable_metrics:
                self._metrics["stream_errors"] += 1
            return False

    def is_connected(self) -> bool:
        """Enhanced connection status check (like SSE)."""
        if not self._initialized or not self._read_stream or not self._write_stream:
            return False

        # Check if we've had too many consecutive failures (like SSE)
        if self._consecutive_failures >= self._max_consecutive_failures:
            logger.warning("Connection marked unhealthy after %d failures", self._consecutive_failures)
            return False

        return True

    async def get_tools(self) -> list[dict[str, Any]]:
        """Enhanced tools retrieval with error handling."""
        if not self._initialized:
            logger.error("Cannot get tools: transport not initialized")
            return []

        start_time = time.time()
        try:
            tools_response = await asyncio.wait_for(
                send_tools_list(self._read_stream, self._write_stream), timeout=self.default_timeout
            )

            # Normalize response
            if isinstance(tools_response, dict):
                tools = tools_response.get("tools", [])
            elif isinstance(tools_response, list):
                tools = tools_response
            else:
                logger.warning("Unexpected tools response type: %s", type(tools_response))
                tools = []

            # Reset failure count on success
            self._consecutive_failures = 0

            if self.enable_metrics:
                response_time = time.time() - start_time
                logger.debug("Retrieved %d tools in %.3fs", len(tools), response_time)

            return tools

        except TimeoutError:
            logger.error("Get tools timed out")
            self._consecutive_failures += 1
            return []
        except Exception as e:
            logger.error("Error getting tools: %s", e)
            self._consecutive_failures += 1
            if self.enable_metrics:
                self._metrics["stream_errors"] += 1
            return []

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any], timeout: float | None = None
    ) -> dict[str, Any]:
        """Enhanced tool calling with recovery and health monitoring."""
        if not self._initialized:
            return {"isError": True, "error": "Transport not initialized"}

        tool_timeout = timeout or self.default_timeout
        start_time = time.time()

        if self.enable_metrics:
            self._metrics["total_calls"] += 1

        try:
            logger.debug("Calling tool '%s' with timeout %ss", tool_name, tool_timeout)

            # Enhanced connection check with recovery attempt
            if not self.is_connected():
                logger.warning("Connection unhealthy, attempting recovery...")
                if not await self._attempt_recovery():
                    if self.enable_metrics:
                        self._update_metrics(time.time() - start_time, False)
                    return {"isError": True, "error": "Failed to recover connection"}

            raw_response = await asyncio.wait_for(
                send_tools_call(self._read_stream, self._write_stream, tool_name, arguments), timeout=tool_timeout
            )

            response_time = time.time() - start_time
            result = self._normalize_mcp_response(raw_response)

            # Reset failure count on success
            self._consecutive_failures = 0
            self._last_successful_ping = time.time()  # Update health timestamp

            if self.enable_metrics:
                self._update_metrics(response_time, not result.get("isError", False))

            if not result.get("isError", False):
                logger.debug("Tool '%s' completed successfully in %.3fs", tool_name, response_time)
            else:
                logger.warning(
                    "Tool '%s' failed in %.3fs: %s", tool_name, response_time, result.get("error", "Unknown error")
                )

            return result

        except TimeoutError:
            response_time = time.time() - start_time
            self._consecutive_failures += 1
            if self.enable_metrics:
                self._update_metrics(response_time, False)

            error_msg = f"Tool execution timed out after {tool_timeout}s"
            logger.error("Tool '%s' %s", tool_name, error_msg)
            return {"isError": True, "error": error_msg}
        except Exception as e:
            response_time = time.time() - start_time
            self._consecutive_failures += 1
            if self.enable_metrics:
                self._update_metrics(response_time, False)
                self._metrics["stream_errors"] += 1

            # Enhanced connection error detection
            error_str = str(e).lower()
            if any(indicator in error_str for indicator in ["connection", "disconnected", "broken pipe", "eof"]):
                logger.warning("Connection error detected: %s", e)
                self._initialized = False
                if self.enable_metrics:
                    self._metrics["connection_errors"] += 1

            error_msg = f"Tool execution failed: {str(e)}"
            logger.error("Tool '%s' error: %s", tool_name, error_msg)
            return {"isError": True, "error": error_msg}

    def _update_metrics(self, response_time: float, success: bool) -> None:
        """Enhanced metrics tracking (like SSE)."""
        if success:
            self._metrics["successful_calls"] += 1
        else:
            self._metrics["failed_calls"] += 1

        self._metrics["total_time"] += response_time
        if self._metrics["total_calls"] > 0:
            self._metrics["avg_response_time"] = self._metrics["total_time"] / self._metrics["total_calls"]

    async def list_resources(self) -> dict[str, Any]:
        """Enhanced resource listing with error handling."""
        if not self._initialized:
            return {}

        try:
            response = await asyncio.wait_for(
                send_resources_list(self._read_stream, self._write_stream), timeout=self.default_timeout
            )
            return response if isinstance(response, dict) else {}
        except TimeoutError:
            logger.error("List resources timed out")
            self._consecutive_failures += 1
            return {}
        except Exception as e:
            logger.debug("Error listing resources: %s", e)
            self._consecutive_failures += 1
            return {}

    async def list_prompts(self) -> dict[str, Any]:
        """Enhanced prompt listing with error handling."""
        if not self._initialized:
            return {}

        try:
            response = await asyncio.wait_for(
                send_prompts_list(self._read_stream, self._write_stream), timeout=self.default_timeout
            )
            return response if isinstance(response, dict) else {}
        except TimeoutError:
            logger.error("List prompts timed out")
            self._consecutive_failures += 1
            return {}
        except Exception as e:
            logger.debug("Error listing prompts: %s", e)
            self._consecutive_failures += 1
            return {}

    async def read_resource(self, uri: str) -> dict[str, Any]:
        """Read a specific resource."""
        if not self._initialized:
            return {}

        try:
            response = await asyncio.wait_for(
                send_resources_read(self._read_stream, self._write_stream, uri), timeout=self.default_timeout
            )
            return response if isinstance(response, dict) else {}
        except TimeoutError:
            logger.error("Read resource timed out")
            self._consecutive_failures += 1
            return {}
        except Exception as e:
            logger.debug("Error reading resource: %s", e)
            self._consecutive_failures += 1
            return {}

    async def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Get a specific prompt."""
        if not self._initialized:
            return {}

        try:
            response = await asyncio.wait_for(
                send_prompts_get(self._read_stream, self._write_stream, name, arguments or {}),
                timeout=self.default_timeout,
            )
            return response if isinstance(response, dict) else {}
        except TimeoutError:
            logger.error("Get prompt timed out")
            self._consecutive_failures += 1
            return {}
        except Exception as e:
            logger.debug("Error getting prompt: %s", e)
            self._consecutive_failures += 1
            return {}

    def get_metrics(self) -> dict[str, Any]:
        """Enhanced metrics with health information."""
        metrics = self._metrics.copy()
        metrics.update(
            {
                "is_connected": self.is_connected(),
                "consecutive_failures": self._consecutive_failures,
                "last_successful_ping": self._last_successful_ping,
                "max_consecutive_failures": self._max_consecutive_failures,
            }
        )
        return metrics

    def reset_metrics(self) -> None:
        """Enhanced metrics reset preserving health state."""
        preserved_init_time = self._metrics.get("initialization_time")
        preserved_last_ping = self._metrics.get("last_ping_time")

        self._metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_time": 0.0,
            "avg_response_time": 0.0,
            "last_ping_time": preserved_last_ping,
            "initialization_time": preserved_init_time,
            "connection_resets": self._metrics.get("connection_resets", 0),
            "stream_errors": 0,
            "connection_errors": 0,
            "recovery_attempts": 0,
        }

    def get_streams(self) -> list[tuple]:
        """Enhanced streams access with connection check."""
        if self._initialized and self._read_stream and self._write_stream:
            return [(self._read_stream, self._write_stream)]
        return []

    async def __aenter__(self):
        """Enhanced context manager entry."""
        success = await self.initialize()
        if not success:
            raise RuntimeError("Failed to initialize HTTPStreamableTransport")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Enhanced context manager cleanup."""
        await self.close()
