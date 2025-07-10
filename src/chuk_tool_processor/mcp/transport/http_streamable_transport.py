# chuk_tool_processor/mcp/transport/http_streamable_transport.py
from __future__ import annotations

import asyncio
import json
import time
from typing import Dict, Any, List, Optional
import logging

from .base_transport import MCPBaseTransport

# Import chuk-mcp HTTP transport components
try:
    from chuk_mcp.transports.http import http_client
    from chuk_mcp.transports.http.parameters import StreamableHTTPParameters
    from chuk_mcp.protocol.messages import (
        send_initialize,
        send_ping, 
        send_tools_list,
        send_tools_call,
    )
    HAS_HTTP_SUPPORT = True
except ImportError:
    HAS_HTTP_SUPPORT = False

# Import optional resource and prompt support
try:
    from chuk_mcp.protocol.messages import (
        send_resources_list,
        send_resources_read,
        send_prompts_list,
        send_prompts_get,
    )
    HAS_RESOURCES_PROMPTS = True
except ImportError:
    HAS_RESOURCES_PROMPTS = False

logger = logging.getLogger(__name__)


class HTTPStreamableTransport(MCPBaseTransport):
    """
    HTTP Streamable transport using chuk-mcp HTTP client.
    
    This implements the modern MCP spec (2025-03-26) replacement for SSE transport.
    Follows the same patterns as SSETransport but uses HTTP requests instead of SSE.
    """

    def __init__(self, url: str, api_key: Optional[str] = None, 
                 connection_timeout: float = 30.0, default_timeout: float = 30.0,
                 session_id: Optional[str] = None, enable_metrics: bool = True):
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
        
        # State tracking (following SSE pattern)
        self._http_context = None
        self._read_stream = None
        self._write_stream = None
        self._initialized = False
        
        # Performance metrics (enhanced from SSE version)
        self._metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_time": 0.0,
            "avg_response_time": 0.0,
            "last_ping_time": None,
            "initialization_time": None
        }
        
        if not HAS_HTTP_SUPPORT:
            logger.warning("HTTP Streamable transport not available - operations will fail")
        if not HAS_RESOURCES_PROMPTS:
            logger.debug("Resources/prompts not available in chuk-mcp")

    async def initialize(self) -> bool:
        """Initialize using chuk-mcp http_client (following SSE pattern)."""
        if not HAS_HTTP_SUPPORT:
            logger.error("HTTP Streamable transport not available in chuk-mcp")
            return False
            
        if self._initialized:
            logger.warning("Transport already initialized")
            return True
        
        start_time = time.time()
        
        try:
            logger.info(f"Initializing HTTP Streamable transport to {self.url}")
            
            # Create HTTP parameters for chuk-mcp (following SSE pattern)
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
                logger.debug("API key configured for authentication")
            
            if self.session_id:
                headers["X-Session-ID"] = self.session_id
                logger.debug(f"Using session ID: {self.session_id}")
            
            http_params = StreamableHTTPParameters(
                url=self.url,
                timeout=self.connection_timeout,
                headers=headers,
                bearer_token=self.api_key,
                session_id=self.session_id,
                enable_streaming=True,  # Enable SSE streaming when available
                max_concurrent_requests=10
            )
            
            # Create and enter the HTTP context (same pattern as SSE)
            self._http_context = http_client(http_params)
            
            logger.debug("Establishing HTTP connection and MCP handshake...")
            self._read_stream, self._write_stream = await asyncio.wait_for(
                self._http_context.__aenter__(),
                timeout=self.connection_timeout
            )
            
            # At this point, chuk-mcp should have established the HTTP connection
            # Verify the connection works with a simple ping (same as SSE)
            logger.debug("Verifying connection with ping...")
            ping_start = time.time()
            ping_success = await asyncio.wait_for(
                send_ping(self._read_stream, self._write_stream),
                timeout=5.0
            )
            ping_time = time.time() - ping_start
            
            if ping_success:
                self._initialized = True
                init_time = time.time() - start_time
                self._metrics["initialization_time"] = init_time
                self._metrics["last_ping_time"] = ping_time
                
                logger.info(f"HTTP Streamable transport initialized successfully in {init_time:.3f}s (ping: {ping_time:.3f}s)")
                return True
            else:
                logger.warning("HTTP connection established but ping failed")
                # Still consider it initialized since connection was established (same as SSE)
                self._initialized = True
                self._metrics["initialization_time"] = time.time() - start_time
                return True

        except asyncio.TimeoutError:
            logger.error(f"HTTP Streamable initialization timed out after {self.connection_timeout}s")
            logger.error("This may indicate the server is not responding to MCP initialization")
            await self._cleanup()
            return False
        except Exception as e:
            logger.error(f"Error initializing HTTP Streamable transport: {e}", exc_info=True)
            await self._cleanup()
            return False

    async def close(self) -> None:
        """Close the HTTP Streamable transport properly (same pattern as SSE)."""
        if not self._initialized:
            return
        
        # Log final metrics (enhanced from SSE)
        if self.enable_metrics and self._metrics["total_calls"] > 0:
            logger.info(
                f"HTTP Streamable transport closing - Total calls: {self._metrics['total_calls']}, "
                f"Success rate: {(self._metrics['successful_calls']/self._metrics['total_calls']*100):.1f}%, "
                f"Avg response time: {self._metrics['avg_response_time']:.3f}s"
            )
            
        try:
            if self._http_context is not None:
                await self._http_context.__aexit__(None, None, None)
                logger.debug("HTTP Streamable context closed")
                
        except Exception as e:
            logger.debug(f"Error during transport close: {e}")
        finally:
            await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up internal state (same as SSE)."""
        self._http_context = None
        self._read_stream = None
        self._write_stream = None
        self._initialized = False

    async def send_ping(self) -> bool:
        """Send ping with performance tracking (enhanced from SSE)."""
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
                logger.debug(f"Ping completed in {ping_time:.3f}s: {result}")
            
            return bool(result)
        except asyncio.TimeoutError:
            logger.error("Ping timed out")
            return False
        except Exception as e:
            logger.error(f"Ping failed: {e}")
            return False

    async def get_tools(self) -> List[Dict[str, Any]]:
        """Get tools list with performance tracking (enhanced from SSE)."""
        if not self._initialized:
            logger.error("Cannot get tools: transport not initialized")
            return []
        
        start_time = time.time()
        try:
            tools_response = await asyncio.wait_for(
                send_tools_list(self._read_stream, self._write_stream),
                timeout=self.default_timeout
            )
            
            # Normalize response (same as SSE)
            if isinstance(tools_response, dict):
                tools = tools_response.get("tools", [])
            elif isinstance(tools_response, list):
                tools = tools_response
            else:
                logger.warning(f"Unexpected tools response type: {type(tools_response)}")
                tools = []
            
            if self.enable_metrics:
                response_time = time.time() - start_time
                logger.debug(f"Retrieved {len(tools)} tools in {response_time:.3f}s")
            
            return tools
            
        except asyncio.TimeoutError:
            logger.error("Get tools timed out")
            return []
        except Exception as e:
            logger.error(f"Error getting tools: {e}")
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
            logger.debug(f"Calling tool '{tool_name}' with timeout {tool_timeout}s")
            
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
            result = self._normalize_tool_response(raw_response)
            
            if self.enable_metrics:
                self._update_metrics(response_time, not result.get("isError", False))
                
            if not result.get("isError", False):
                logger.debug(f"Tool '{tool_name}' completed successfully in {response_time:.3f}s")
            else:
                logger.warning(f"Tool '{tool_name}' failed in {response_time:.3f}s: {result.get('error', 'Unknown error')}")
            
            return result

        except asyncio.TimeoutError:
            response_time = time.time() - start_time
            if self.enable_metrics:
                self._update_metrics(response_time, False)
                
            error_msg = f"Tool execution timed out after {tool_timeout}s"
            logger.error(f"Tool '{tool_name}' {error_msg}")
            return {
                "isError": True,
                "error": error_msg
            }
        except Exception as e:
            response_time = time.time() - start_time
            if self.enable_metrics:
                self._update_metrics(response_time, False)
                
            error_msg = f"Tool execution failed: {str(e)}"
            logger.error(f"Tool '{tool_name}' error: {error_msg}")
            return {
                "isError": True,
                "error": error_msg
            }

    def _update_metrics(self, response_time: float, success: bool) -> None:
        """Update performance metrics (new feature)."""
        if success:
            self._metrics["successful_calls"] += 1
        else:
            self._metrics["failed_calls"] += 1
            
        self._metrics["total_time"] += response_time
        self._metrics["avg_response_time"] = (
            self._metrics["total_time"] / self._metrics["total_calls"]
        )

    async def list_resources(self) -> Dict[str, Any]:
        """List resources using chuk-mcp (same as SSE)."""
        if not HAS_RESOURCES_PROMPTS:
            logger.debug("Resources/prompts not available in chuk-mcp")
            return {}
            
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
            logger.debug(f"Error listing resources: {e}")
            return {}

    async def list_prompts(self) -> Dict[str, Any]:
        """List prompts using chuk-mcp (same as SSE)."""
        if not HAS_RESOURCES_PROMPTS:
            logger.debug("Resources/prompts not available in chuk-mcp")
            return {}
            
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
            logger.debug(f"Error listing prompts: {e}")
            return {}

    def _normalize_tool_response(self, raw_response: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize response for backward compatibility (same as SSE)."""
        # Handle explicit error in response
        if "error" in raw_response:
            error_info = raw_response["error"]
            if isinstance(error_info, dict):
                error_msg = error_info.get("message", "Unknown error")
            else:
                error_msg = str(error_info)
            
            return {
                "isError": True,
                "error": error_msg
            }

        # Handle successful response with result
        if "result" in raw_response:
            result = raw_response["result"]
            
            if isinstance(result, dict) and "content" in result:
                return {
                    "isError": False,
                    "content": self._extract_content(result["content"])
                }
            else:
                return {
                    "isError": False,
                    "content": result
                }

        # Handle direct content-based response
        if "content" in raw_response:
            return {
                "isError": False,
                "content": self._extract_content(raw_response["content"])
            }

        # Fallback
        return {
            "isError": False,
            "content": raw_response
        }

    def _extract_content(self, content_list: Any) -> Any:
        """Extract content from MCP content format (same as SSE)."""
        if not isinstance(content_list, list) or not content_list:
            return content_list
        
        # Handle single content item
        if len(content_list) == 1:
            content_item = content_list[0]
            if isinstance(content_item, dict):
                if content_item.get("type") == "text":
                    text_content = content_item.get("text", "")
                    # Try to parse JSON, fall back to plain text
                    try:
                        return json.loads(text_content)
                    except json.JSONDecodeError:
                        return text_content
                else:
                    return content_item
        
        # Multiple content items
        return content_list

    def get_streams(self) -> List[tuple]:
        """Provide streams for backward compatibility (same as SSE)."""
        if self._initialized and self._read_stream and self._write_stream:
            return [(self._read_stream, self._write_stream)]
        return []

    def is_connected(self) -> bool:
        """Check connection status (same as SSE)."""
        return self._initialized and self._read_stream is not None and self._write_stream is not None

    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics (new feature)."""
        return self._metrics.copy()

    def reset_metrics(self) -> None:
        """Reset performance metrics (new feature)."""
        self._metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_time": 0.0,
            "avg_response_time": 0.0,
            "last_ping_time": self._metrics.get("last_ping_time"),
            "initialization_time": self._metrics.get("initialization_time")
        }

    async def __aenter__(self):
        """Context manager support (same as SSE)."""
        success = await self.initialize()
        if not success:
            raise RuntimeError("Failed to initialize HTTP Streamable transport")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup (same as SSE)."""
        await self.close()

    def __repr__(self) -> str:
        """Enhanced string representation for debugging."""
        status = "initialized" if self._initialized else "not initialized"
        metrics_info = ""
        if self.enable_metrics and self._metrics["total_calls"] > 0:
            success_rate = (self._metrics["successful_calls"] / self._metrics["total_calls"]) * 100
            metrics_info = f", calls: {self._metrics['total_calls']}, success: {success_rate:.1f}%"
        
        return f"HTTPStreamableTransport(status={status}, url={self.url}{metrics_info})"