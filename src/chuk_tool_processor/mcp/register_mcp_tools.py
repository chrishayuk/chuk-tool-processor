# chuk_tool_processor/mcp/register_mcp_tools.py
"""
Registration functions for MCP tools.
"""

from typing import List, Dict, Any

from chuk_tool_processor.mcp.mcp_tool import MCPTool
from chuk_tool_processor.mcp.stream_manager import StreamManager
from chuk_tool_processor.registry.provider import ToolRegistryProvider
from chuk_tool_processor.logging import get_logger

logger = get_logger("chuk_tool_processor.mcp.register")


def register_mcp_tools(
    stream_manager: StreamManager,
    namespace: str = "mcp"
) -> List[str]:
    """
    Register MCP tools with the CHUK registry.
    
    Args:
        stream_manager: StreamManager instance
        namespace: Namespace for the tools
        
    Returns:
        List of registered tool names
    """
    registry = ToolRegistryProvider.get_registry()
    registered_tools = []
    
    # Get all tools from StreamManager
    mcp_tools = stream_manager.get_all_tools()
    
    for tool_def in mcp_tools:
        tool_name = tool_def.get("name")
        if not tool_name:
            logger.warning("Tool definition missing name")
            continue
            
        description = tool_def.get("description", f"MCP tool: {tool_name}")
        
        try:
            # Create tool
            tool = MCPTool(tool_name, stream_manager)
            
            # Register with registry under the original name in the given namespace
            registry.register_tool(
                tool,
                name=tool_name,
                namespace=namespace,
                metadata={
                    "description": description,
                    "is_async": True,
                    "tags": {"mcp", "remote"},
                    "argument_schema": tool_def.get("inputSchema", {})
                }
            )
            
            # Also register the tool in the default namespace with the namespaced name
            # This allows calling the tool as either "echo" or "stdio.echo" from parsers
            namespaced_tool_name = f"{namespace}.{tool_name}"
            registry.register_tool(
                tool,
                name=namespaced_tool_name,
                namespace="default",
                metadata={
                    "description": description,
                    "is_async": True,
                    "tags": {"mcp", "remote", "namespaced"},
                    "argument_schema": tool_def.get("inputSchema", {})
                }
            )
            
            registered_tools.append(tool_name)
            logger.info(f"Registered MCP tool '{tool_name}' in namespace '{namespace}' (also as '{namespaced_tool_name}' in default)")
            
        except Exception as e:
            logger.error(f"Error registering MCP tool '{tool_name}': {e}")
    
    return registered_tools