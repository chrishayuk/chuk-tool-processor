# examples/mcp_stdio_example.py
"""
Example demonstrating flexible MCP integration with support for multiple transport types.
"""
import asyncio
import os
import sys
import json
from typing import Dict, List

# Add project root to path if running as script
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# CHUK Tool Processor imports
from chuk_tool_processor.mcp import setup_mcp_stdio, setup_mcp_sse
from chuk_tool_processor.registry import ToolRegistryProvider

async def stdio_example():
    """Example using stdio transport."""
    print("\n=== MCP with Stdio Transport ===")
    
    # Server configuration
    config_file = "server_config.json"
    
    # Create or update config file for the example
    if not os.path.exists(config_file):
        server_config = {
            "mcpServers": {
                "echo": {
                    "command": "uv",
                    "args": ["--directory", "/Users/christopherhay/chris-source/agent-x/mcp-servers/chuk-mcp-echo-server", "run", "src/chuk_mcp_echo_server/main.py"]
                }
            }
        }
        
        with open(config_file, "w") as f:
            json.dump(server_config, f)
        print(f"Created config file: {config_file}")
    else:
        print(f"Using existing config file: {config_file}")
    
    servers = ["echo"]
    server_names = {0: "echo"}
    
    try:
        processor, stream_manager = await setup_mcp_stdio(
            config_file=config_file,
            servers=servers,
            server_names=server_names,
            namespace="stdio"
        )
        
        registry = ToolRegistryProvider.get_registry()
        tools = [t for t in registry.list_tools() if t[0] == "stdio"]
        print(f"Registered stdio tools ({len(tools)}):")
        for namespace, name in tools:
            metadata = registry.get_metadata(name, namespace)
            description = metadata.description if metadata else "No description"
            print(f"  - {namespace}.{name}: {description}")
        
        # Example LLM text with tool calls - use fully-qualified default namespace name
        llm_text = """
        I'll echo your message using stdio transport.
        
        <tool name=\"stdio.echo\" args='{"message": "Hello from stdio transport!"}'/>
        """
        
        print("\nProcessing LLM text...")
        results = await processor.process_text(llm_text)
        
        if results:
            print("\nResults:")
            for result in results:
                print(f"Tool: {result.tool}")
                if result.error:
                    print(f"  Error: {result.error}")
                else:
                    print(f"  Result: {json.dumps(result.result, indent=2) if isinstance(result.result, dict) else result.result}")
                print(f"  Duration: {(result.end_time - result.start_time).total_seconds():.3f}s")
        else:
            print("\nNo tool calls found or executed.")
            
        await stream_manager.close()
        
    except Exception as e:
        print(f"Error in stdio example: {e}")
        import traceback
        traceback.print_exc()

async def sse_example():
    """Example using SSE transport."""
    print("\n=== MCP with SSE Transport ===")
    
    sse_servers = [
        {
            "name": "weather",
            "url": "https://api.example.com/sse/weather",
            "api_key": "your_api_key_here"
        }
    ]
    server_names = {0: "weather"}
    
    try:
        processor, stream_manager = await setup_mcp_sse(
            servers=sse_servers,
            server_names=server_names,
            namespace="sse"
        )
        
        registry = ToolRegistryProvider.get_registry()
        tools = [t for t in registry.list_tools() if t[0] == "sse"]
        print(f"Registered SSE tools ({len(tools)}):")
        for namespace, name in tools:
            metadata = registry.get_metadata(name, namespace)
            description = metadata.description if metadata else "No description"
            print(f"  - {namespace}.{name}: {description}")
        
        print("\nNote: SSE transport is currently a placeholder implementation.")
        
        await stream_manager.close()
        
    except Exception as e:
        print(f"Error in SSE example: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """Run the examples."""
    print("\n=== Flexible MCP Integration Example ===")
    await stdio_example()
    #await sse_example()
    
    registry = ToolRegistryProvider.get_registry()
    all_tools = registry.list_tools()
    
    print("\n=== All Registered Tools ===")
    print(f"Total tools: {len(all_tools)}")
    
    by_namespace = {}
    for namespace, name in all_tools:
        by_namespace.setdefault(namespace, []).append(name)
        
    for namespace, tools in by_namespace.items():
        print(f"\nNamespace: {namespace} ({len(tools)} tools)")
        for name in tools:
            metadata = registry.get_metadata(name, namespace)
            description = metadata.description if metadata else "No description"
            print(f"  - {name}: {description}")

if __name__ == "__main__":
    asyncio.run(main())
