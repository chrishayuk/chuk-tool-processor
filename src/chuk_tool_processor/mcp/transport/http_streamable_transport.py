# chuk_tool_processor/mcp/transport/http_streamable_transport.py
from __future__ import annotations

import asyncio
import json
import time
from typing import Dict, Any, List, Optional
import logging

from .base_transport import MCPBaseTransport

# Import latest chuk-mcp HTTP Streamable transport
# Try different possible naming conventions
try:
    # First try the expected naming
    from chuk_mcp.transports.http_streamable import http_streamable_client
    from chuk_mcp.transports.http_streamable.parameters import HTTPStreamableParameters
    HAS_HTTP_STREAMABLE_SUPPORT = True
    STREAMABLE_CLIENT = http_streamable_client
    STREAMABLE_PARAMS = HTTPStreamableParameters
except ImportError:
    try:
        # Try alternative naming
        from chuk_mcp.transports.streamable_http import streamable_http_client
        from chuk_mcp.transports.streamable_http.parameters import StreamableHttpParameters
        HAS_HTTP_STREAMABLE_SUPPORT = True
        STREAMABLE_CLIENT = streamable_http_client
        STREAMABLE_PARAMS = StreamableHttpParameters
    except ImportError:
        HAS_HTTP_STREAMABLE_SUPPORT = False

# Import protocol messages
try:
    from chuk_mcp.protocol.messages import (
        send_ping, 
        send_tools_list,
        send_tools_call,
        send_resources_list,
        send_prompts_list,
    )
    HAS_PROTOCOL_MESSAGES = True
except ImportError:
    HAS_PROTOCOL_MESSAGES = False

logger = logging.getLogger(__name__)


class HTTPStreamableTransport(MCPBaseTransport):
    """
    Enhanced HTTP Streamable transport using latest chuk-mcp APIs.
    
    This implements the modern Streamable HTTP transport (spec 2025-03-26)
    which replaces the deprecated SSE transport with a cleaner, more flexible approach.
    
    Key features:
    - Single /mcp endpoint for all communication
    - Works with standard HTTP infrastructure  
    - Supports both immediate and streaming responses
    - Better error handling and retry logic
    - Stateless operation when streaming not needed
    """

    def __init__(self, url: str, api_key: Optional[str] = None, 
                 connection_timeout: float = 30.0, default_timeout: float = 30.0,
                 session_id: Optional[str] = None, enable_metrics: bool = True):
        """
        Initialize HTTP Streamable transport.
        
        Args:
            url: Base URL of the MCP server (will append /mcp if needed)
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
        
        # State tracking
        self._streamable_context = None
        self._read_stream = None
        self._write_stream = None
        self._initialized = False
        
        # Performance metrics
        self._metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_time": 0.0,
            "avg_response_time": 0.0,
            "last_ping_time": None,
            "initialization_time": None
        }
        
        if not HAS_HTTP_STREAMABLE_SUPPORT:
            logger.warning("HTTP Streamable transport not available - operations will fail")
        if not HAS_PROTOCOL_MESSAGES:
            logger.warning("Protocol messages not available - operations will fail")

    async def initialize(self) -> bool:
        """Initialize using latest chuk-mcp streamable http client with enhanced monitoring."""
        if not HAS_HTTP_STREAMABLE_SUPPORT or not HAS_PROTOCOL_MESSAGES:
            logger.error("HTTP Streamable transport or protocol messages not available in chuk-mcp")
            return False
            
        if self._initialized:
            logger.warning("Transport already initialized")
            return True
        
        start_time = time.time()
        
        try:
            logger.info(f"Initializing HTTP Streamable transport to {self.url}")
            
            # Create HTTP Streamable parameters
            streamable_params = STREAMABLE_PARAMS(
                url=self.url,
                timeout=self.connection_timeout,
            )
            
            # Add session ID if provided
            if self.session_id:
                streamable_params.session_id = self.session_id
                logger.debug(f"Using session ID: {self.session_id}")
            
            # Add API key via headers if provided
            if self.api_key:
                streamable_params.headers = {"Authorization": f"Bearer {self.api_key}"}
                logger.debug("API key configured for authentication")
            
            # Create and enter the context - let chuk-mcp handle MCP handshake
            self._streamable_context = STREAMABLE_CLIENT(streamable_params)
            
            logger.debug("Establishing HTTP Streamable connection...")
            self._read_stream, self._write_stream = await asyncio.wait_for(
                self._streamable_context.__aenter__(),
                timeout=self.connection_timeout
            )
            
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
                init_time = time.time() - start_time
                self._metrics["initialization_time"] = init_time
                self._metrics["last_ping_time"] = ping_time
                
                logger.info(f"HTTP Streamable transport initialized successfully in {init_time:.3f}s (ping: {ping_time:.3f}s)")
                return True
            else:
                logger.warning("HTTP Streamable connection established but ping failed")
                # Still consider it initialized since connection was established
                self._initialized = True
                self._metrics["initialization_time"] = time.time() - start_time
                return True

        except asyncio.TimeoutError:
            logger.error(f"HTTP Streamable initialization timed out after {self.connection_timeout}s")
            await self._cleanup()
            return False
        except Exception as e:
            logger.error(f"Error initializing HTTP Streamable transport: {e}", exc_info=True)
            await self._cleanup()
            return False

    async def close(self) -> None:
        """Close the HTTP Streamable transport properly with metrics summary."""
        if not self._initialized:
            return
        
        # Log final metrics
        if self.enable_metrics and self._metrics["total_calls"] > 0:
            logger.info(
                f"HTTP Streamable transport closing - Total calls: {self._metrics['total_calls']}, "
                f"Success rate: {(self._metrics['successful_calls']/self._metrics['total_calls']*100):.1f}%, "
                f"Avg response time: {self._metrics['avg_response_time']:.3f}s"
            )
            
        try:
            if self._streamable_context is not None:
                await self._streamable_context.__aexit__(None, None, None)
                logger.debug("HTTP Streamable context closed")
                
        except Exception as e:
            logger.debug(f"Error during transport close: {e}")
        finally:
            await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up internal state."""
        self._streamable_context = None
        self._read_stream = None
        self._write_stream = None
        self._initialized = False

    async def send_ping(self) -> bool:
        """Send ping with performance tracking."""
        if not self._initialized or not self._read_stream:
            return False
        
        start_time = time.time()
        try:
            result = await asyncio.wait_for(
                send_ping(self._read_stream, self._write_stream),
                timeout=5.0
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
        """Update performance metrics."""
        if success:
            self._metrics["successful_calls"] += 1
        else:
            self._metrics["failed_calls"] += 1
            
        self._metrics["total_time"] += response_time
        self._metrics["avg_response_time"] = (
            self._metrics["total_time"] / self._metrics["total_calls"]
        )

    async def list_resources(self) -> Dict[str, Any]:
        """List resources using latest chuk-mcp."""
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
        """List prompts using latest chuk-mcp."""
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
        """Normalize response for backward compatibility."""
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
        """Extract content from MCP content format with enhanced error handling."""
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
        """Provide streams for backward compatibility."""
        if self._initialized and self._read_stream and self._write_stream:
            return [(self._read_stream, self._write_stream)]
        return []

    def is_connected(self) -> bool:
        """Check connection status."""
        return self._initialized and self._read_stream is not None and self._write_stream is not None

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
            "initialization_time": self._metrics.get("initialization_time")
        }

    async def __aenter__(self):
        """Context manager support."""
        success = await self.initialize()
        if not success:
            raise RuntimeError("Failed to initialize HTTP Streamable transport")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        await self.close()

    def __repr__(self) -> str:
        """Enhanced string representation for debugging."""
        status = "initialized" if self._initialized else "not initialized"
        metrics_info = ""
        if self.enable_metrics and self._metrics["total_calls"] > 0:
            success_rate = (self._metrics["successful_calls"] / self._metrics["total_calls"]) * 100
            metrics_info = f", calls: {self._metrics['total_calls']}, success: {success_rate:.1f}%"
        
        return f"HTTPStreamableTransport(status={status}, url={self.url}{metrics_info})"