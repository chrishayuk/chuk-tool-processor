# chuk_tool_processor/mcp/mcp_tool.py
"""
MCP tool that uses StreamManager for execution.
"""

from typing import Any

from chuk_tool_processor.mcp.stream_manager import StreamManager
from chuk_tool_processor.logging import get_logger

logger = get_logger("chuk_tool_processor.mcp.mcp_tool")

class MCPTool:
    """
    MCP tool that uses StreamManager for execution.
    
    This tool handles both namespaced and non-namespaced execution.
    """
    
    def __init__(self, tool_name: str, stream_manager: StreamManager):
        """
        Initialize the MCP tool.
        
        Args:
            tool_name: Name of the MCP tool
            stream_manager: StreamManager instance
        """
        self.tool_name = tool_name
        self.stream_manager = stream_manager
        
    async def execute(self, **kwargs: Any) -> Any:
        """
        Execute the tool using StreamManager.
        
        Args:
            **kwargs: Tool arguments
            
        Returns:
            Tool result
        """
        logger.debug(f"Executing MCP tool {self.tool_name}")
        
        result = await self.stream_manager.call_tool(
            tool_name=self.tool_name,
            arguments=kwargs
        )
        
        if result.get("isError"):
            error_msg = result.get("error", "Unknown error")
            logger.error(f"Error executing MCP tool {self.tool_name}: {error_msg}")
            raise RuntimeError(error_msg)
            
        return result.get("content")