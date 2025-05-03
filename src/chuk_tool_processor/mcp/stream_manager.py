# chuk_tool_processor/mcp/stream_manager.py
"""
StreamManager for CHUK Tool Processor.
"""
from __future__ import annotations

import asyncio
import json
from typing import Dict, List, Optional, Any

# tool processor imports
from chuk_mcp.config import load_config
from chuk_tool_processor.mcp.transport import MCPBaseTransport, StdioTransport, SSETransport
from chuk_tool_processor.logging import get_logger

# logger
logger = get_logger("chuk_tool_processor.mcp.stream_manager")

class StreamManager:
    """
    Manager for MCP server streams with support for multiple transport types.
    """
    
    def __init__(self):
        """Initialize the StreamManager."""
        self.transports: Dict[str, MCPBaseTransport] = {}
        self.server_info: List[Dict[str, Any]] = []
        self.tool_to_server_map: Dict[str, str] = {}
        self.server_names: Dict[int, str] = {}
        self.all_tools: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        
    @classmethod
    async def create(
        cls,
        config_file: str,
        servers: List[str],
        server_names: Optional[Dict[int, str]] = None,
        transport_type: str = "stdio"
    ) -> StreamManager:
        """
        Create and initialize a StreamManager.
        
        Args:
            config_file: Path to the config file
            servers: List of server names to connect to
            server_names: Optional mapping of server indices to names
            transport_type: Transport type ("stdio" or "sse")
            
        Returns:
            Initialized StreamManager
        """
        manager = cls()
        await manager.initialize(config_file, servers, server_names, transport_type)
        return manager
        
    @classmethod
    async def create_with_sse(
        cls,
        servers: List[Dict[str, str]],
        server_names: Optional[Dict[int, str]] = None
    ) -> StreamManager:
        """
        Create and initialize a StreamManager with SSE transport.
        
        Args:
            servers: List of server configurations with "name" and "url" keys
            server_names: Optional mapping of server indices to names
            
        Returns:
            Initialized StreamManager
        """
        manager = cls()
        await manager.initialize_with_sse(servers, server_names)
        return manager
        
    async def initialize(
        self,
        config_file: str,
        servers: List[str],
        server_names: Optional[Dict[int, str]] = None,
        transport_type: str = "stdio"
    ) -> None:
        """
        Initialize the StreamManager.
        
        Args:
            config_file: Path to the config file
            servers: List of server names to connect to
            server_names: Optional mapping of server indices to names
            transport_type: Transport type ("stdio" or "sse")
        """
        async with self._lock:
            # Store server names mapping
            self.server_names = server_names or {}
            
            # Initialize servers
            for i, server_name in enumerate(servers):
                try:
                    if transport_type == "stdio":
                        # Load configuration
                        server_params = await load_config(config_file, server_name)
                        
                        # Create transport
                        transport = StdioTransport(server_params)
                    elif transport_type == "sse":
                        # For SSE, we would parse the config differently
                        # This is just a placeholder
                        transport = SSETransport("http://localhost:8000")
                    else:
                        logger.error(f"Unsupported transport type: {transport_type}")
                        continue
                    
                    # Initialize transport
                    if not await transport.initialize():
                        logger.error(f"Failed to initialize transport for server: {server_name}")
                        continue
                        
                    # Store transport
                    self.transports[server_name] = transport
                    
                    # Check server is responsive
                    ping_result = await transport.send_ping()
                    status = "Up" if ping_result else "Down"
                    
                    # Get available tools
                    tools = await transport.get_tools()
                    
                    # Map tools to server
                    for tool in tools:
                        tool_name = tool.get("name")
                        if tool_name:
                            self.tool_to_server_map[tool_name] = server_name
                    
                    # Add to all tools
                    self.all_tools.extend(tools)
                    
                    # Add server info
                    self.server_info.append({
                        "id": i,
                        "name": server_name,
                        "tools": len(tools),
                        "status": status
                    })
                    
                    logger.info(f"Initialized server {server_name} with {len(tools)} tools")
                    
                except Exception as e:
                    logger.error(f"Error initializing server {server_name}: {e}")
                    
            logger.info(f"StreamManager initialized with {len(self.transports)} servers and {len(self.all_tools)} tools")
            
    async def initialize_with_sse(
        self,
        servers: List[Dict[str, str]],
        server_names: Optional[Dict[int, str]] = None
    ) -> None:
        """
        Initialize the StreamManager with SSE transport.
        
        Args:
            servers: List of server configurations with "name" and "url" keys
            server_names: Optional mapping of server indices to names
        """
        async with self._lock:
            # Store server names mapping
            self.server_names = server_names or {}
            
            # Initialize servers
            for i, server_config in enumerate(servers):
                server_name = server_config.get("name")
                url = server_config.get("url")
                api_key = server_config.get("api_key")
                
                if not server_name or not url:
                    logger.error(f"Invalid server configuration: {server_config}")
                    continue
                
                try:
                    # Create transport
                    transport = SSETransport(url, api_key)
                    
                    # Initialize transport
                    if not await transport.initialize():
                        logger.error(f"Failed to initialize SSE transport for server: {server_name}")
                        continue
                        
                    # Store transport
                    self.transports[server_name] = transport
                    
                    # Check server is responsive
                    ping_result = await transport.send_ping()
                    status = "Up" if ping_result else "Down"
                    
                    # Get available tools
                    tools = await transport.get_tools()
                    
                    # Map tools to server
                    for tool in tools:
                        tool_name = tool.get("name")
                        if tool_name:
                            self.tool_to_server_map[tool_name] = server_name
                    
                    # Add to all tools
                    self.all_tools.extend(tools)
                    
                    # Add server info
                    self.server_info.append({
                        "id": i,
                        "name": server_name,
                        "tools": len(tools),
                        "status": status
                    })
                    
                    logger.info(f"Initialized SSE server {server_name} with {len(tools)} tools")
                    
                except Exception as e:
                    logger.error(f"Error initializing SSE server {server_name}: {e}")
            
            logger.info(f"StreamManager initialized with {len(self.transports)} SSE servers and {len(self.all_tools)} tools")
    
    def get_all_tools(self) -> List[Dict[str, Any]]:
        """
        Get all available tools.
        
        Returns:
            List of tool definitions
        """
        return self.all_tools
        
    def get_server_for_tool(self, tool_name: str) -> Optional[str]:
        """
        Get the server name for a tool.
        
        Args:
            tool_name: Tool name
            
        Returns:
            Server name or None if not found
        """
        return self.tool_to_server_map.get(tool_name)
        
    def get_server_info(self) -> List[Dict[str, Any]]:
        """
        Get information about all servers.
        
        Returns:
            List of server info dictionaries
        """
        return self.server_info
        
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        server_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Call a tool.
        
        Args:
            tool_name: Tool name
            arguments: Tool arguments
            server_name: Optional server name override
            
        Returns:
            Tool result
        """
        # Get server name
        if not server_name:
            server_name = self.get_server_for_tool(tool_name)
            
        if not server_name or server_name not in self.transports:
            return {
                "isError": True,
                "error": f"No server found for tool: {tool_name}"
            }
            
        # Get transport
        transport = self.transports[server_name]
        
        # Call tool
        return await transport.call_tool(tool_name, arguments)
    
    async def close(self) -> None:
        """Close all transports."""
        close_tasks = []
        for name, transport in self.transports.items():
            close_tasks.append(transport.close())
        
        if close_tasks:
            try:
                await asyncio.gather(*close_tasks)
            except asyncio.CancelledError:
                # Ignore cancellation during cleanup
                pass
            except Exception as e:
                logger.error(f"Error closing transports: {e}")
        
        self.transports.clear()
        self.server_info.clear()
        self.tool_to_server_map.clear()
        self.all_tools.clear()