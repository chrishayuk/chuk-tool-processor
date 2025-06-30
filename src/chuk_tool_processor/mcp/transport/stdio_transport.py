# chuk_tool_processor/mcp/transport/stdio_transport.py
from __future__ import annotations

import asyncio
import json
from typing import Dict, Any, List, Optional
import logging

# ------------------------------------------------------------------ #
#  Local import                                                      #
# ------------------------------------------------------------------ #
from .base_transport import MCPBaseTransport

# ------------------------------------------------------------------ #
#  New chuk-mcp API imports only                                    #
# ------------------------------------------------------------------ #
from chuk_mcp.transports.stdio import stdio_client
from chuk_mcp.transports.stdio.parameters import StdioParameters

from chuk_mcp.protocol.messages import (
    send_initialize,
    send_ping,
    send_tools_list,
    send_tools_call,
)

# Try to import resources and prompts if available
try:
    from chuk_mcp.protocol.messages import (
        send_resources_list,
        send_resources_read,
    )
    HAS_RESOURCES = True
except ImportError:
    HAS_RESOURCES = False

try:
    from chuk_mcp.protocol.messages import (
        send_prompts_list,
        send_prompts_get,
    )
    HAS_PROMPTS = True
except ImportError:
    HAS_PROMPTS = False

logger = logging.getLogger(__name__)


class StdioTransport(MCPBaseTransport):
    """
    STDIO transport for MCP communication using new chuk-mcp APIs.
    """

    def __init__(self, server_params):
        """
        Initialize STDIO transport.
        
        Args:
            server_params: Either a dict with 'command' and 'args', 
                          or a StdioParameters object
        """
        # Convert dict format to StdioParameters
        if isinstance(server_params, dict):
            self.server_params = StdioParameters(
                command=server_params.get('command', 'python'),
                args=server_params.get('args', [])
            )
        else:
            self.server_params = server_params
        
        self.read_stream = None
        self.write_stream = None
        self._client_context = None

    # --------------------------------------------------------------------- #
    #  Connection management                                                #
    # --------------------------------------------------------------------- #
    async def initialize(self) -> bool:
        """Initialize the STDIO transport."""
        try:
            logger.info("Initializing STDIO transport...")
            
            # Use the new stdio_client context manager
            self._client_context = stdio_client(self.server_params)
            self.read_stream, self.write_stream = await self._client_context.__aenter__()
            
            # Send initialize message
            logger.debug("Sending initialize message...")
            init_result = await send_initialize(self.read_stream, self.write_stream)
            
            if init_result:
                logger.info("STDIO transport initialized successfully")
                return True
            else:
                logger.error("Initialize message failed")
                await self._cleanup()
                return False

        except Exception as e:
            logger.error(f"Error initializing STDIO transport: {e}", exc_info=True)
            await self._cleanup()
            return False

    async def close(self) -> None:
        """Close the transport with proper error handling."""
        try:
            # Handle both old _context_stack and new _client_context for test compatibility
            if hasattr(self, '_context_stack') and self._context_stack:
                try:
                    await self._context_stack.__aexit__(None, None, None)
                    logger.debug("Context stack closed")
                except asyncio.CancelledError:
                    # Expected during shutdown - don't log as error
                    logger.debug("Context stack close cancelled during shutdown")
                except Exception as e:
                    logger.error(f"Error closing context stack: {e}")
            elif self._client_context:
                try:
                    await self._client_context.__aexit__(None, None, None)
                    logger.debug("STDIO client context closed")
                except asyncio.CancelledError:
                    # Expected during shutdown - don't log as error
                    logger.debug("Client context close cancelled during shutdown")
                except Exception as e:
                    logger.error(f"Error closing client context: {e}")
        except Exception as e:
            logger.error(f"Error during transport cleanup: {e}")
        finally:
            await self._cleanup()

    async def _cleanup(self) -> None:
        """Internal cleanup method."""
        # Clean up both old and new context attributes for test compatibility
        if hasattr(self, '_context_stack'):
            self._context_stack = None
        self._client_context = None
        self.read_stream = None
        self.write_stream = None

    # --------------------------------------------------------------------- #
    #  Core MCP Operations                                                  #
    # --------------------------------------------------------------------- #
    async def send_ping(self) -> bool:
        """Send a ping."""
        if not self.read_stream or not self.write_stream:
            logger.error("Cannot send ping: streams not available")
            return False
        
        try:
            result = await send_ping(self.read_stream, self.write_stream)
            logger.debug(f"Ping result: {result}")
            return bool(result)
        except Exception as e:
            logger.error(f"Ping failed: {e}")
            return False

    async def get_tools(self) -> List[Dict[str, Any]]:
        """Get list of available tools."""
        if not self.read_stream or not self.write_stream:
            logger.error("Cannot get tools: streams not available")
            return []
        
        try:
            tools_response = await send_tools_list(self.read_stream, self.write_stream)
            
            # Handle both dict response and direct tools list
            if isinstance(tools_response, dict):
                tools = tools_response.get("tools", [])
            elif isinstance(tools_response, list):
                tools = tools_response
            else:
                logger.warning(f"Unexpected tools response type: {type(tools_response)}")
                tools = []
            
            logger.debug(f"Retrieved {len(tools)} tools")
            return tools
            
        except Exception as e:
            logger.error(f"Error getting tools: {e}")
            return []

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool.
        
        Returns normalized response in format:
        {
            "isError": bool,
            "content": Any,  # Result data if successful
            "error": str     # Error message if failed
        }
        """
        if not self.read_stream or not self.write_stream:
            return {
                "isError": True,
                "error": "Transport not initialized"
            }

        try:
            logger.debug(f"Calling tool {tool_name} with args: {arguments}")
            
            raw_response = await send_tools_call(
                self.read_stream, 
                self.write_stream, 
                tool_name, 
                arguments
            )
            
            logger.debug(f"Tool {tool_name} raw response: {raw_response}")
            return self._normalize_tool_response(raw_response)

        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            return {
                "isError": True,
                "error": f"Tool execution failed: {str(e)}"
            }

    def _normalize_tool_response(self, raw_response: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize tool response to consistent format."""
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

        # Handle successful response with result (MCP standard)
        if "result" in raw_response:
            result = raw_response["result"]
            
            # If result has content, extract it
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

        # Fallback: return whatever the server sent
        return {
            "isError": False,
            "content": raw_response
        }

    def _extract_content(self, content_list: Any) -> Any:
        """Extract content from MCP content list format."""
        if not isinstance(content_list, list) or not content_list:
            return content_list
        
        # Handle single content item (most common)
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
                    # Non-text content (image, audio, etc.)
                    return content_item
        
        # Multiple content items - return the list
        return content_list

    # --------------------------------------------------------------------- #
    #  Resources Operations (if available)                                 #
    # --------------------------------------------------------------------- #
    async def list_resources(self) -> Dict[str, Any]:
        """Get list of available resources."""
        if not HAS_RESOURCES:
            logger.warning("Resources not supported in current chuk-mcp version")
            return {}
            
        if not self.read_stream or not self.write_stream:
            logger.error("Cannot list resources: streams not available")
            return {}
        
        try:
            response = await send_resources_list(self.read_stream, self.write_stream)
            return response if isinstance(response, dict) else {}
        except Exception as e:
            logger.error(f"Error listing resources: {e}")
            return {}

    async def read_resource(self, uri: str) -> Dict[str, Any]:
        """Read a specific resource by URI."""
        if not HAS_RESOURCES:
            logger.warning("Resources not supported in current chuk-mcp version")
            return {}
            
        if not self.read_stream or not self.write_stream:
            logger.error("Cannot read resource: streams not available")
            return {}
        
        try:
            response = await send_resources_read(self.read_stream, self.write_stream, uri)
            return response if isinstance(response, dict) else {}
        except Exception as e:
            logger.error(f"Error reading resource {uri}: {e}")
            return {}

    # --------------------------------------------------------------------- #
    #  Prompts Operations (if available)                                   #
    # --------------------------------------------------------------------- #
    async def list_prompts(self) -> Dict[str, Any]:
        """Get list of available prompts."""
        if not HAS_PROMPTS:
            logger.warning("Prompts not supported in current chuk-mcp version")
            return {}
            
        if not self.read_stream or not self.write_stream:
            logger.error("Cannot list prompts: streams not available")
            return {}
        
        try:
            response = await send_prompts_list(self.read_stream, self.write_stream)
            return response if isinstance(response, dict) else {}
        except Exception as e:
            logger.error(f"Error listing prompts: {e}")
            return {}

    async def get_prompt(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get a specific prompt by name."""
        if not HAS_PROMPTS:
            logger.warning("Prompts not supported in current chuk-mcp version")
            return {}
            
        if not self.read_stream or not self.write_stream:
            logger.error("Cannot get prompt: streams not available")
            return {}
        
        try:
            response = await send_prompts_get(
                self.read_stream, 
                self.write_stream, 
                name, 
                arguments or {}
            )
            return response if isinstance(response, dict) else {}
        except Exception as e:
            logger.error(f"Error getting prompt {name}: {e}")
            return {}

    # --------------------------------------------------------------------- #
    #  Utility Methods                                                      #
    # --------------------------------------------------------------------- #
    def get_streams(self) -> List[tuple]:
        """Get the underlying streams for advanced usage."""
        if self.read_stream and self.write_stream:
            return [(self.read_stream, self.write_stream)]
        return []

    def is_connected(self) -> bool:
        """Check if transport is connected and ready."""
        return self.read_stream is not None and self.write_stream is not None

    async def __aenter__(self):
        """Async context manager entry."""
        success = await self.initialize()
        if not success:
            raise RuntimeError("Failed to initialize STDIO transport")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    def __repr__(self) -> str:
        """String representation for debugging."""
        status = "connected" if self.is_connected() else "disconnected"
        cmd_info = f"command={getattr(self.server_params, 'command', 'unknown')}"
        return f"StdioTransport(status={status}, {cmd_info})"