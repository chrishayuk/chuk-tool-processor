#!/usr/bin/env python
# examples/debug_timeout_strategy.py
"""
Debug the timeout handling in InProcessStrategy to identify why
some calls use wrong timeout values.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.registry.provider import ToolRegistryProvider
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.mcp.setup_mcp_sse import setup_mcp_sse

async def debug_timeout_handling():
    """Debug timeout configuration in the execution strategy."""
    
    print("=== Debugging Timeout Strategy Handling ===\n")
    
    # Connect to mock server
    try:
        print("1. Connecting to mock MCP SSE server...")
        _, stream_manager = await setup_mcp_sse(
            servers=[
                {
                    "name": "mock_server",
                    "url": "http://localhost:8020",
                }
            ],
            server_names={0: "mock_server"},
            namespace="sse",
        )
        print("✅ Connected successfully")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return
    
    registry = await ToolRegistryProvider.get_registry()
    
    # Test different timeout configurations
    timeout_configs = [
        {"timeout": 1.0, "description": "1 second timeout"},
        {"timeout": 2.0, "description": "2 second timeout"},
        {"timeout": 3.0, "description": "3 second timeout"},
        {"timeout": 15.0, "description": "15 second timeout"},
    ]
    
    for config in timeout_configs:
        timeout = config["timeout"]
        description = config["description"]
        
        print(f"\n2. Testing {description}...")
        
        # Create strategy with specific timeout
        strategy = InProcessStrategy(
            registry,
            default_timeout=timeout
        )
        
        executor = ToolExecutor(registry=registry, strategy=strategy)
        
        # Create a test call
        test_call = ToolCall(
            tool="perplexity_search",
            namespace="sse",
            arguments={"query": f"Test query with {timeout}s timeout"}
        )
        
        print(f"   Strategy timeout: {strategy.default_timeout}")
        print(f"   Executing tool call...")
        
        try:
            import time
            start_time = time.time()
            
            results = await executor.execute([test_call])
            
            duration = time.time() - start_time
            result = results[0]
            
            print(f"   ✅ Completed in {duration:.3f}s")
            print(f"   Result duration: {(result.end_time - result.start_time).total_seconds():.3f}s")
            
            if result.error:
                print(f"   ⚠️  Error: {result.error}")
            else:
                print(f"   📝 Success: {str(result.result)[:100]}...")
                
        except Exception as e:
            duration = time.time() - start_time
            print(f"   ❌ Failed after {duration:.3f}s: {e}")
    
    # Test parallel execution with timeout debugging
    print(f"\n3. Testing parallel execution timeout behavior...")
    
    strategy = InProcessStrategy(
        registry,
        default_timeout=2.0  # 2 second timeout
    )
    
    executor = ToolExecutor(registry=registry, strategy=strategy)
    
    # Create multiple parallel calls
    parallel_calls = [
        ToolCall(
            tool="perplexity_search",
            namespace="sse",
            arguments={"query": f"Parallel test query {i}"}
        )
        for i in range(3)
    ]
    
    print(f"   Strategy timeout: {strategy.default_timeout}")
    print(f"   Executing {len(parallel_calls)} parallel calls...")
    
    try:
        import time
        start_time = time.time()
        
        results = await executor.execute(parallel_calls)
        
        total_duration = time.time() - start_time
        print(f"   ✅ All completed in {total_duration:.3f}s")
        
        for i, (call, result) in enumerate(zip(parallel_calls, results)):
            duration = (result.end_time - result.start_time).total_seconds()
            status = "✅" if result.error is None else "❌"
            
            print(f"   Call {i+1}: {status} {duration:.3f}s")
            if result.error:
                print(f"     Error: {result.error}")
            else:
                print(f"     Success: {str(result.result)[:50]}...")
                
    except Exception as e:
        total_duration = time.time() - start_time
        print(f"   ❌ Parallel execution failed after {total_duration:.3f}s: {e}")
    
    # Investigate individual wrapper timeout settings
    print(f"\n4. Investigating individual tool wrapper timeouts...")
    
    for tool_name in ["perplexity_search", "perplexity_deep_research", "perplexity_quick_fact"]:
        wrapper_cls = await registry.get_tool(tool_name, "sse")
        if wrapper_cls:
            try:
                wrapper = wrapper_cls()
                
                # Check if wrapper has timeout attributes
                timeout_attrs = []
                for attr in dir(wrapper):
                    if 'timeout' in attr.lower():
                        value = getattr(wrapper, attr, None)
                        timeout_attrs.append(f"{attr}={value}")
                
                print(f"   🔧 {tool_name}:")
                if timeout_attrs:
                    print(f"     Timeout attributes: {', '.join(timeout_attrs)}")
                else:
                    print(f"     No timeout attributes found")
                    
                # Check metadata
                metadata = await registry.get_metadata(tool_name, "sse")
                if metadata:
                    if hasattr(metadata, 'timeout'):
                        print(f"     Metadata timeout: {metadata.timeout}")
                    else:
                        print(f"     No metadata timeout")
                        
            except Exception as e:
                print(f"   ❌ {tool_name}: Failed to inspect - {e}")
    
    # Cleanup
    await stream_manager.close()
    print(f"\n✅ Timeout debugging completed!")

if __name__ == "__main__":
    asyncio.run(debug_timeout_handling())