#!/usr/bin/env python
# examples/debug_timeout_source.py
"""
Trace the exact source of the 10-second timeout by instrumenting all timeout-related calls.
"""

import asyncio
import sys
import time
import inspect
from pathlib import Path
from unittest.mock import patch, AsyncMock

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.registry.provider import ToolRegistryProvider
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.mcp.setup_mcp_sse import setup_mcp_sse

# Store original functions
original_wait_for = asyncio.wait_for

def get_call_stack():
    """Get a simplified call stack for debugging."""
    stack = inspect.stack()
    relevant_frames = []
    for frame in stack[2:8]:  # Skip this function and the wrapper
        filename = Path(frame.filename).name
        relevant_frames.append(f"{filename}:{frame.lineno}:{frame.function}")
    return " -> ".join(relevant_frames)

async def traced_wait_for(coro, timeout=None):
    """Trace all asyncio.wait_for calls with their timeouts."""
    caller_stack = get_call_stack()
    print(f"   🔍 asyncio.wait_for(timeout={timeout}s) from: {caller_stack}")
    
    start_time = time.time()
    try:
        result = await original_wait_for(coro, timeout)
        duration = time.time() - start_time
        print(f"   ✅ wait_for completed in {duration:.3f}s (limit: {timeout}s)")
        return result
    except asyncio.TimeoutError:
        duration = time.time() - start_time
        print(f"   ⏰ wait_for TIMED OUT after {duration:.3f}s (limit: {timeout}s)")
        raise
    except Exception as e:
        duration = time.time() - start_time
        print(f"   ❌ wait_for failed after {duration:.3f}s: {e}")
        raise

async def debug_timeout_source():
    """Debug to find the exact source of the 10-second timeout."""
    
    print("=== Tracing Timeout Sources ===\n")
    
    # Patch asyncio.wait_for globally
    with patch('asyncio.wait_for', traced_wait_for):
        # Also patch it in specific modules that might import it
        with patch('chuk_tool_processor.execution.strategies.inprocess_strategy.asyncio.wait_for', traced_wait_for):
            with patch('chuk_tool_processor.mcp.stream_manager.asyncio.wait_for', traced_wait_for):
                
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
                    print("✅ Connected successfully\n")
                except Exception as e:
                    print(f"❌ Connection failed: {e}")
                    return
                
                registry = await ToolRegistryProvider.get_registry()
                
                # Test with 1 second timeout to see where the 10s comes from
                print(f"2. Testing 1 second timeout with comprehensive tracing...")
                
                strategy = InProcessStrategy(
                    registry,
                    default_timeout=1.0
                )
                
                executor = ToolExecutor(registry=registry, strategy=strategy)
                
                test_call = ToolCall(
                    tool="perplexity_search",
                    namespace="sse",
                    arguments={"query": "Timeout tracing test"}
                )
                
                print(f"   Strategy default_timeout: {strategy.default_timeout}")
                print(f"   Executing with full timeout tracing...\n")
                
                try:
                    start_time = time.time()
                    
                    results = await executor.execute([test_call])
                    
                    duration = time.time() - start_time
                    result = results[0]
                    
                    print(f"\n   ✅ Total execution completed in {duration:.3f}s")
                    print(f"   Result duration: {(result.end_time - result.start_time).total_seconds():.3f}s")
                    
                    if result.error:
                        print(f"   ⚠️  Error: {result.error}")
                        
                        # Check if error message contains timeout info
                        if "timeout" in result.error.lower():
                            print(f"   🔍 Timeout error detected! Message: {result.error}")
                    else:
                        print(f"   📝 Success")
                        
                except Exception as e:
                    duration = time.time() - start_time
                    print(f"\n   ❌ Failed after {duration:.3f}s: {e}")
                
                # Also test the StreamManager call_tool directly
                print(f"\n3. Testing StreamManager.call_tool directly...")
                
                try:
                    start_time = time.time()
                    
                    # Call the stream manager directly to see if it has its own timeout
                    result = await stream_manager.call_tool(
                        tool_name="perplexity_search",
                        arguments={"query": "Direct StreamManager test"}
                    )
                    
                    duration = time.time() - start_time
                    print(f"   ✅ Direct call completed in {duration:.3f}s")
                    
                    if result.get("isError"):
                        print(f"   ⚠️  Error: {result.get('error')}")
                    else:
                        print(f"   📝 Success")
                        
                except Exception as e:
                    duration = time.time() - start_time
                    print(f"   ❌ Direct call failed after {duration:.3f}s: {e}")
                
                # Test transport layer directly
                print(f"\n4. Testing transport layer...")
                
                transport = stream_manager.transports.get("mock_server")
                if transport:
                    try:
                        start_time = time.time()
                        
                        result = await transport.call_tool(
                            "perplexity_search",
                            {"query": "Direct transport test"}
                        )
                        
                        duration = time.time() - start_time
                        print(f"   ✅ Transport call completed in {duration:.3f}s")
                        
                        if result.get("isError"):
                            print(f"   ⚠️  Error: {result.get('error')}")
                        else:
                            print(f"   📝 Success")
                            
                    except Exception as e:
                        duration = time.time() - start_time
                        print(f"   ❌ Transport call failed after {duration:.3f}s: {e}")
                else:
                    print("   ❌ No transport found for mock_server")
                
                # Cleanup
                await stream_manager.close()
                print(f"\n✅ Timeout source tracing completed!")

if __name__ == "__main__":
    asyncio.run(debug_timeout_source())