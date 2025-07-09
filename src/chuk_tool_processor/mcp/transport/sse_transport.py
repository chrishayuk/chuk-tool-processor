# chuk_tool_processor/mcp/transport/sse_transport.py
from __future__ import annotations

import asyncio
import json
from typing import Dict, Any, List, Optional
import logging

from .base_transport import MCPBaseTransport

# Import latest chuk-mcp SSE transport
try:
    from chuk_mcp.transports.sse import sse_client
    from chuk_mcp.transports.sse.parameters import SSEParameters
    from chuk_mcp.protocol.messages import (
        send_initialize,
        send_ping, 
        send_tools_list,
        send_tools_call,
    )
    HAS_SSE_SUPPORT = True
except ImportError:
    HAS_SSE_SUPPORT = False

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


class SSETransport(MCPBaseTransport):
    """
    Updated SSE transport using latest chuk-mcp APIs.
    
    Supports all required abstract methods and provides full MCP functionality.
    """

    def __init__(self, url: str, api_key: Optional[str] = None, 
                 connection_timeout: float = 30.0, default_timeout: float = 30.0):
        """
        Initialize SSE transport with latest chuk-mcp.
        
        Args:
            url: SSE server URL
            api_key: Optional API key for authentication
            connection_timeout: Timeout for initial connection
            default_timeout: Default timeout for operations
        """
        self.url = url
        self.api_key = api_key
        self.connection_timeout = connection_timeout
        self.default_timeout = default_timeout
        
        # State tracking
        self._sse_context = None
        self._read_stream = None
        self._write_stream = None
        self._initialized = False
        
        if not HAS_SSE_SUPPORT:
            logger.warning("SSE transport not available - operations will fail")

    async def initialize(self) -> bool:
        """Initialize using latest chuk-mcp sse_client."""
        if not HAS_SSE_SUPPORT:
            logger.error("SSE transport not available in chuk-mcp")
            return False
            
        if self._initialized:
            logger.warning("Transport already initialized")
            return True
            
        try:
            logger.info("Initializing SSE transport...")
            
            # Create SSE parameters for latest chuk-mcp
            sse_params = SSEParameters(
                url=self.url,
                timeout=self.connection_timeout,
                auto_reconnect=True,
                max_reconnect_attempts=3
            )
            
            # Create and enter the context - this should handle the full MCP handshake
            self._sse_context = sse_client(sse_params)
            
            # The sse_client should handle the entire initialization process
            logger.debug("Establishing SSE connection and MCP handshake...")
            self._read_stream, self._write_stream = await asyncio.wait_for(
                self._sse_context.__aenter__(),
                timeout=self.connection_timeout
            )
            
            # At this point, chuk-mcp should have already completed the MCP initialization
            # Let's verify the connection works with a simple ping
            logger.debug("Verifying connection with ping...")
            ping_success = await asyncio.wait_for(
                send_ping(self._read_stream, self._write_stream),
                timeout=5.0
            )
            
            if ping_success:
                self._initialized = True
                logger.info("SSE transport initialized successfully")
                return True
            else:
                logger.warning("SSE connection established but ping failed")
                # Still consider it initialized since connection was established
                self._initialized = True
                return True

        except asyncio.TimeoutError:
            logger.error(f"SSE initialization timed out after {self.connection_timeout}s")
            logger.error("This may indicate the server is not responding to MCP initialization")
            await self._cleanup()
            return False
        except Exception as e:
            logger.error(f"Error initializing SSE transport: {e}", exc_info=True)
            await self._cleanup()
            return False

    async def close(self) -> None:
        """Close the SSE transport properly."""
        if not self._initialized:
            return
            
        try:
            if self._sse_context is not None:
                await self._sse_context.__aexit__(None, None, None)
                logger.debug("SSE context closed")
                
        except Exception as e:
            logger.debug(f"Error during transport close: {e}")
        finally:
            await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up internal state."""
        self._sse_context = None
        self._read_stream = None
        self._write_stream = None
        self._initialized = False

    async def send_ping(self) -> bool:
        """Send ping using latest chuk-mcp."""
        if not self._initialized:
            logger.error("Cannot send ping: transport not initialized")
            return False
        
        try:
            result = await asyncio.wait_for(
                send_ping(self._read_stream, self._write_stream),
                timeout=self.default_timeout
            )
            logger.debug(f"Ping result: {result}")
            return bool(result)
        except asyncio.TimeoutError:
            logger.error("Ping timed out")
            return False
        except Exception as e:
            logger.error(f"Ping failed: {e}")
            return False

    async def get_tools(self) -> List[Dict[str, Any]]:
        """Get tools list using latest chuk-mcp."""
        if not self._initialized:
            logger.error("Cannot get tools: transport not initialized")
            return []
        
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
            
            logger.debug(f"Retrieved {len(tools)} tools")
            return tools
            
        except asyncio.TimeoutError:
            logger.error("Get tools timed out")
            return []
        except Exception as e:
            logger.error(f"Error getting tools: {e}")
            return []

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], 
                       timeout: Optional[float] = None) -> Dict[str, Any]:
        """Call tool using latest chuk-mcp."""
        if not self._initialized:
            return {
                "isError": True,
                "error": "Transport not initialized"
            }

        tool_timeout = timeout or self.default_timeout

        try:
            logger.debug(f"Calling tool {tool_name} with args: {arguments}")
            
            raw_response = await asyncio.wait_for(
                send_tools_call(
                    self._read_stream, 
                    self._write_stream, 
                    tool_name, 
                    arguments
                ),
                timeout=tool_timeout
            )
            
            logger.debug(f"Tool {tool_name} raw response: {raw_response}")
            return self._normalize_tool_response(raw_response)

        except asyncio.TimeoutError:
            logger.error(f"Tool {tool_name} timed out after {tool_timeout}s")
            return {
                "isError": True,
                "error": f"Tool execution timed out after {tool_timeout}s"
            }
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            return {
                "isError": True,
                "error": f"Tool execution failed: {str(e)}"
            }

    async def list_resources(self) -> Dict[str, Any]:
        """List resources using latest chuk-mcp."""
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
        """List prompts using latest chuk-mcp."""
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
        """Extract content from MCP content format."""
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

    async def __aenter__(self):
        """Context manager support."""
        success = await self.initialize()
        if not success:
            raise RuntimeError("Failed to initialize SSE transport")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        await self.close()

    def __repr__(self) -> str:
        """String representation for debugging."""
        status = "initialized" if self._initialized else "not initialized"
        return f"SSETransport(status={status}, url={self.url})"