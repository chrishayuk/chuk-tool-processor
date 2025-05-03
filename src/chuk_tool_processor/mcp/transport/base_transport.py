# chuk_tool_processor/mcp/transport/base_transport.py
"""
Abstract transport layer for MCP communication.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List

class MCPBaseTransport(ABC):
    """
    Abstract base class for MCP transport mechanisms.
    """
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize the transport connection.
        
        Returns:
            True if successful, False otherwise
        """
        pass
        
    @abstractmethod
    async def send_ping(self) -> bool:
        """
        Send a ping message.
        
        Returns:
            True if successful, False otherwise
        """
        pass
        
    @abstractmethod
    async def get_tools(self) -> List[Dict[str, Any]]:
        """
        Get available tools.
        
        Returns:
            List of tool definitions
        """
        pass
        
    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a tool.
        
        Args:
            tool_name: Tool name
            arguments: Tool arguments
            
        Returns:
            Tool result
        """
        pass
        
    @abstractmethod
    async def close(self) -> None:
        """Close the transport connection."""
        pass



   