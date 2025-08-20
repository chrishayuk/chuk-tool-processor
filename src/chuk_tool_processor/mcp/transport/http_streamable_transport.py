# chuk_tool_processor/mcp/transport/http_streamable_transport.py - FIXED
from __future__ import annotations

import asyncio
import json
import time
from typing import Dict, Any, List, Optional
import logging

from .base_transport import MCPBaseTransport

# Import chuk-mcp HTTP transport components
from chuk_mcp.transports.http import http_client
from chuk_mcp.transports.http.parameters import StreamableHTTPParameters
from chuk_mcp.protocol.messages import (
    send_initialize,
    send_ping, 
    send_tools_list,
    send_tools_call,
    send_resources_list,
    send_resources_read,
    send_prompts_list,
    send_prompts_get,
)

logger = logging.getLogger(__name__)


class HTTPStreamableTransport(MCPBaseTransport):
    """
    HTTP Streamable transport using chuk-mcp HTTP client.
    
    FIXED: Improved connection management and parameter configuration
    to eliminate "server disconnected" errors.
    """

    def __init__(self, url: str, api_key: Optional[str] = None, 
                 connection_timeout: float = 30.0, 
                 default_timeout: float = 30.0,
                 session_id: Optional[str] = None, 
                 enable_metrics: bool = True):
        """
        Initialize HTTP Streamable transport with chuk-mcp.
        
        Args:
            url: HTTP server URL (should end with /mcp)
            api_key: Optional API key for authentication
            connection_timeout: Timeout for initial connection
            default_timeout: Default timeout for operations
            session_id: Optional session ID for stateful connections
            enable_metrics: Whether to track performance metrics
        """
        # Ensure URL points to the /mcp endpoint
        if not url.endswith('/mcp'):
            self.url = f"{url.rstrip('/')}/mcp"
        else:
            self.url = url
            
        self.api_key = api_key
        self.connection_timeout = connection_timeout
        self.default_timeout = default_timeout
        self.session_id = session_id
        self.enable_metrics = enable_metrics
        
        logger.debug("HTTP Streamable transport initialized with URL: %s", self.url)
        if self.api_key:
            logger.debug("API key configured for authentication")
        if self.session_id:
            logger.debug("Session ID configured: %s", self.session_id)
        
        # State tracking
        self._http_context = None
        self._read_stream = None
        self._write_stream = None
        self._initialized = False
        
        # Performance metrics (consistent with other transports)
        self._metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_time": 0.0,
            "avg_response_time": 0.0,
            "last_ping_time": None,
            "initialization_time": None,
            "connection_resets": 0,
            "stream_errors": 0
        }

    async def initialize(self) -> bool:
        """Initialize using chuk-mcp http_client with improved configuration."""
        if self._initialized:
            logger.warning("Transport already initialized")
            return True
        
        start_time = time.time()
        
        try:
            logger.debug("Initializing HTTP Streamable transport to %s", self.url)
            
            # FIXED: Proper HTTP headers (match working diagnostic)
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            
            # FIXED: Only set Authorization header, not both bearer_token and headers
            bearer_token = None
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
                logger.debug("API key configured for authentication")
            
            if self.session_id:
                headers["X-Session-ID"] = self.session_id
                logger.debug("Using session ID: %s", self.session_id)
            
            # FIXED: Use only valid StreamableHTTPParameters
            http_params = StreamableHTTPParameters(
                url=self.url,
                timeout=self.default_timeout,          # FIXED: Use default_timeout for operations
                headers=headers,
                bearer_token=bearer_token,             # FIXED: Don't duplicate auth
                session_id=self.session_id,
                enable_streaming=True,
                max_concurrent_requests=5,             # FIXED: Reduce concurrency for stability
                max_retries=2,                         # FIXED: Add retry configuration
                retry_delay=1.0,                       # FIXED: Short retry delay
                user_agent="chuk-tool-processor/1.0.0",
            )
            
            # Create and enter the HTTP context
            self._http_context = http_client(http_params)
            
            logger.debug("Establishing HTTP connection and MCP handshake...")
            self._read_stream, self._write_stream = await asyncio.wait_for(
                self._http_context.__aenter__(),
                timeout=self.connection_timeout
            )
            
            # FIXED: Simplified MCP initialize sequence (match working diagnostic)
            logger.debug("Sending MCP initialize request...")
            init_start = time.time()
            
            # Send initialize request with default parameters
            init_result = await asyncio.wait_for(
                send_initialize(self._read_stream, self._write_stream),
                timeout=self.default_timeout
            )
            
            init_time = time.time() - init_start
            logger.debug("MCP initialize completed in %.3fs", init_time)
            
            # Verify the connection works with a simple ping
            logger.debug("Verifying connection with ping...")
            ping_start = time.time()
            ping_success = await asyncio.wait_for(
                send_ping(self._read_stream, self._write_stream),
                timeout=5.0
            )
            ping_time = time.time() - ping_start
            
            if ping_success:
                self._initialized = True
                total_init_time = time.time() - start_time
                if self.enable_metrics:
                    self._metrics["initialization_time"] = total_init_time
                    self._metrics["last_ping_time"] = ping_time
                
                logger.debug("HTTP Streamable transport initialized successfully in %.3fs (ping: %.3fs)", total_init_time, ping_time)
                return True
            else:
                logger.warning("HTTP connection established but ping failed")
                # Still consider it initialized since connection was established
                self._initialized = True
                if self.enable_metrics:
                    self._metrics["initialization_time"] = time.time() - start_time
                return True

        except asyncio.TimeoutError:
            logger.error("HTTP Streamable initialization timed out after %ss", self.connection_timeout)
            logger.error("This may indicate the server is not responding to MCP initialization")
            await self._cleanup()
            return False
        except Exception as e:
            logger.error("Error initializing HTTP Streamable transport: %s", e, exc_info=True)
            await self._cleanup()
            return False

    async def close(self) -> None:
        """Close the HTTP Streamable transport properly."""
        if not self._initialized:
            return
        
        # Log final metrics
        if self.enable_metrics and self._metrics["total_calls"] > 0:
            logger.debug(
                "HTTP Streamable transport closing - Total calls: %d, Success rate: %.1f%%, Avg response time: %.3fs",
                self._metrics["total_calls"],
                (self._metrics["successful_calls"] / self._metrics["total_calls"] * 100),
                self._metrics["avg_response_time"]
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
        """Clean up internal state."""
        self._http_context = None
        self._read_stream = None
        self._write_stream = None
        self._initialized = False

    async def send_ping(self) -> bool:
        """Send ping with performance tracking."""
        if not self._initialized or not self._read_stream:
            logger.error("Cannot send ping: transport not initialized")
            return False
        
        start_time = time.time()
        try:
            result = await asyncio.wait_for(
                send_ping(self._read_stream, self._write_stream),
                timeout=self.default_timeout
            )
            
            if self.enable_metrics:
                ping_time = time.time() - start_time
                self._metrics["last_ping_time"] = ping_time
                logger.debug("HTTP Streamable ping completed in %.3fs: %s", ping_time, result)
            
            return bool(result)
        except asyncio.TimeoutError:
            logger.error("HTTP Streamable ping timed out")
            return False
        except Exception as e:
            logger.error("HTTP Streamable ping failed: %s", e)
            if self.enable_metrics:
                self._metrics["stream_errors"] += 1
            return False

    def is_connected(self) -> bool:
        """Check connection status."""
        return self._initialized and self._read_stream is not None and self._write_stream is not None

    async def get_tools(self) -> List[Dict[str, Any]]:
        """Get tools list with performance tracking."""
        if not self._initialized:
            logger.error("Cannot get tools: transport not initialized")
            return []
        
        start_time = time.time()
        try:
            tools_response = await asyncio.wait_for(
                send_tools_list(self._read_stream, self._write_stream),
                timeout=self.default_timeout
            )
            
            # Normalize response
            if isinstance(tools_response, dict):
                tools = tools_response.get("tools", [])
            elif isinstance(tools_response, list):
                tools = tools_response
            else:
                logger.warning("Unexpected tools response type: %s", type(tools_response))
                tools = []
            
            if self.enable_metrics:
                response_time = time.time() - start_time
                logger.debug("Retrieved %d tools in %.3fs", len(tools), response_time)
            
            return tools
            
        except asyncio.TimeoutError:
            logger.error("Get tools timed out")
            return []
        except Exception as e:
            logger.error("Error getting tools: %s", e)
            if self.enable_metrics:
                self._metrics["stream_errors"] += 1
            return []

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], 
                       timeout: Optional[float] = None) -> Dict[str, Any]:
        """Call tool with enhanced performance tracking and error handling."""
        if not self._initialized:
            return {
                "isError": True,
                "error": "Transport not initialized"
            }

        tool_timeout = timeout or self.default_timeout
        start_time = time.time()
        
        if self.enable_metrics:
            self._metrics["total_calls"] += 1

        try:
            logger.debug("Calling tool '%s' with timeout %ss", tool_name, tool_timeout)
            
            # FIXED: Add connection state check before making call
            if not self.is_connected():
                logger.warning("Connection lost, attempting to reconnect...")
                if not await self.initialize():
                    return {
                        "isError": True,
                        "error": "Failed to reconnect to server"
                    }
            
            raw_response = await asyncio.wait_for(
                send_tools_call(
                    self._read_stream, 
                    self._write_stream, 
                    tool_name, 
                    arguments
                ),
                timeout=tool_timeout
            )
            
            response_time = time.time() - start_time
            result = self._normalize_mcp_response(raw_response)
            
            if self.enable_metrics:
                self._update_metrics(response_time, not result.get("isError", False))
                
            if not result.get("isError", False):
                logger.debug("Tool '%s' completed successfully in %.3fs", tool_name, response_time)
            else:
                logger.warning("Tool '%s' failed in %.3fs: %s", tool_name, response_time, result.get('error', 'Unknown error'))
            
            return result

        except asyncio.TimeoutError:
            response_time = time.time() - start_time
            if self.enable_metrics:
                self._update_metrics(response_time, False)
                
            error_msg = f"Tool execution timed out after {tool_timeout}s"
            logger.error("Tool '%s' %s", tool_name, error_msg)
            return {
                "isError": True,
                "error": error_msg
            }
        except Exception as e:
            response_time = time.time() - start_time
            if self.enable_metrics:
                self._update_metrics(response_time, False)
                self._metrics["stream_errors"] += 1
                
            # FIXED: Check if this is a connection error that should trigger reconnect
            if "connection" in str(e).lower() or "disconnected" in str(e).lower():
                logger.warning("Connection error detected, marking as disconnected: %s", e)
                self._initialized = False
                
            error_msg = f"Tool execution failed: {str(e)}"
            logger.error("Tool '%s' error: %s", tool_name, error_msg)
            return {
                "isError": True,
                "error": error_msg
            }

    def _update_metrics(self, response_time: float, success: bool) -> None:
        """Update performance metrics."""
        if success:
            self._metrics["successful_calls"] += 1
        else:
            self._metrics["failed_calls"] += 1
            
        self._metrics["total_time"] += response_time
        if self._metrics["total_calls"] > 0:
            self._metrics["avg_response_time"] = (
                self._metrics["total_time"] / self._metrics["total_calls"]
            )

    async def list_resources(self) -> Dict[str, Any]:
        """List resources using chuk-mcp."""
        if not self._initialized:
            return {}
        
        try:
            response = await asyncio.wait_for(
                send_resources_list(self._read_stream, self._write_stream),
                timeout=self.default_timeout
            )
            return response if isinstance(response, dict) else {}
        except asyncio.TimeoutError:
            logger.error("List resources timed out")
            return {}
        except Exception as e:
            logger.debug("Error listing resources: %s", e)
            return {}

    async def list_prompts(self) -> Dict[str, Any]:
        """List prompts using chuk-mcp."""
        if not self._initialized:
            return {}
        
        try:
            response = await asyncio.wait_for(
                send_prompts_list(self._read_stream, self._write_stream),
                timeout=self.default_timeout
            )
            return response if isinstance(response, dict) else {}
        except asyncio.TimeoutError:
            logger.error("List prompts timed out")
            return {}
        except Exception as e:
            logger.debug("Error listing prompts: %s", e)
            return {}

    # ------------------------------------------------------------------ #
    #  Metrics and monitoring (consistent with other transports)        #
    # ------------------------------------------------------------------ #
    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics."""
        return self._metrics.copy()

    def reset_metrics(self) -> None:
        """Reset performance metrics."""
        self._metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_time": 0.0,
            "avg_response_time": 0.0,
            "last_ping_time": self._metrics.get("last_ping_time"),
            "initialization_time": self._metrics.get("initialization_time"),
            "connection_resets": self._metrics.get("connection_resets", 0),
            "stream_errors": 0
        }

    # ------------------------------------------------------------------ #
    #  Backward compatibility                                            #
    # ------------------------------------------------------------------ #
    def get_streams(self) -> List[tuple]:
        """Provide streams for backward compatibility."""
        if self._initialized and self._read_stream and self._write_stream:
            return [(self._read_stream, self._write_stream)]
        return []

    # ------------------------------------------------------------------ #
    #  Context manager support                                           #
    # ------------------------------------------------------------------ #
    async def __aenter__(self):
        """Context manager support."""
        success = await self.initialize()
        if not success:
            raise RuntimeError("Failed to initialize HTTPStreamableTransport")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        await self.close()