#!/usr/bin/env python
# examples/mcp_timeout_bug_demo.py
"""
Demonstrate timeout bugs specifically with MCP tools.
"""

import asyncio
import sys
import time
import json
from pathlib import Path
from unittest.mock import patch, AsyncMock
from contextlib import asynccontextmanager

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from chuk_tool_processor.mcp.setup_mcp_sse import setup_mcp_sse
from chuk_tool_processor.models.tool_call import ToolCall

# Global timeout tracking
timeout_calls = []

original_wait_for = asyncio.wait_for

async def tracking_wait_for(coro, timeout=None):
    """Track all timeout calls to expose bugs."""
    import inspect
    
    # Get the calling function
    frame = inspect.currentframe()
    caller_info = "unknown"
    try:
        caller_frame = frame.f_back
        filename = Path(caller_frame.f_code.co_filename).name
        function = caller_frame.f_code.co_name
        line = caller_frame.f_lineno
        caller_info = f"{filename}:{line}:{function}"
    finally:
        del frame
    
    timeout_calls.append({
        "timeout": timeout,
        "caller": caller_info,
        "timestamp": time.time()
    })
    
    print(f"    ⏱️  wait_for(timeout={timeout}s) from {caller_info}")
    
    return await original_wait_for(coro, timeout)

@asynccontextmanager
async def mock_hanging_server():
    """Create a mock server that hangs on tool calls to test timeouts."""
    
    class MockTransport:
        def __init__(self):
            self.initialized = True
            
        async def initialize(self):
            return True
            
        async def close(self):
            pass
            
        async def send_ping(self):
            return True
            
        async def get_tools(self):
            return [
                {
                    "name": "hanging_tool",
                    "description": "A tool that hangs forever",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "message": {"type": "string"}
                        }
                    }
                }
            ]
            
        async def call_tool(self, tool_name: str, arguments: dict):
            print(f"    🕳️  MockTransport.call_tool called - will hang for 20 seconds...")
            # Hang for 20 seconds to test timeout behavior
            await asyncio.sleep(20.0)
            return {
                "isError": False,
                "content": f"Completed {tool_name} after hanging"
            }
    
    # Mock the StreamManager to use our hanging transport
    from chuk_tool_processor.mcp.stream_manager import StreamManager
    
    original_create_with_sse = StreamManager.create_with_sse
    
    async def mock_create_with_sse(cls, servers, server_names=None):
        # Create a real StreamManager but replace its transport
        manager = StreamManager()
        
        # Set up mock data
        mock_transport = MockTransport()
        manager.transports = {"hanging_server": mock_transport}
        manager.server_info = [{"id": 0, "name": "hanging_server", "tools": 1, "status": "Up"}]
        manager.tool_to_server_map = {"hanging_tool": "hanging_server"}
        manager.all_tools = await mock_transport.get_tools()
        
        return manager
    
    # Patch the StreamManager creation
    with patch.object(StreamManager, 'create_with_sse', classmethod(mock_create_with_sse)):
        yield

async def test_mcp_timeout_bug():
    """Test timeout bugs with MCP tools."""
    
    print("=== MCP TIMEOUT BUG DEMONSTRATION ===\n")
    
    global timeout_calls
    timeout_calls = []
    
    # Patch asyncio.wait_for globally to track all timeout calls
    with patch('asyncio.wait_for', tracking_wait_for):
        with patch('chuk_tool_processor.mcp.stream_manager.asyncio.wait_for', tracking_wait_for):
            with patch('chuk_tool_processor.mcp.transport.sse_transport.asyncio.wait_for', tracking_wait_for):
                with patch('chuk_tool_processor.execution.strategies.inprocess_strategy.asyncio.wait_for', tracking_wait_for):
                    
                    async with mock_hanging_server():
                        
                        print("📋 Setting up MCP with hanging server...")
                        
                        # Set up MCP with very short timeout
                        processor, stream_manager = await setup_mcp_sse(
                            servers=[{"name": "hanging_server", "url": "mock://hanging"}],
                            namespace="mcp",
                            default_timeout=2.0  # 2 second timeout
                        )
                        
                        print(f"✅ MCP setup complete\n")
                        
                        # Test 1: Direct processor call with short timeout
                        print("📋 TEST 1: Processor with 3s timeout vs 20s hanging tool")
                        print("   Expected: Should timeout after 3s")
                        print("   Configured processor timeout: 2.0s")
                        print("   Explicit timeout parameter: 3.0s")
                        print("   Tool will hang for: 20.0s")
                        print("   Actual behavior:")
                        
                        timeout_calls.clear()  # Clear previous calls
                        
                        start_time = time.time()
                        try:
                            # Use the processor with explicit timeout
                            results = await processor.process(
                                '<tool name="mcp.hanging_tool" args=\'{"message": "test"}\'/>', 
                                timeout=3.0
                            )
                            
                            duration = time.time() - start_time
                            print(f"   📈 Total duration: {duration:.3f}s")
                            
                            if results:
                                result = results[0]
                                print(f"   📝 Result: {result.result if not result.error else f'ERROR: {result.error}'}")
                            
                            if duration > 5.0:  # Much longer than expected
                                print(f"   🚨 MAJOR BUG: Took {duration:.3f}s but should have timed out at 3.0s!")
                            elif duration > 4.0:  # Slightly longer than expected
                                print(f"   ⚠️  POSSIBLE BUG: Took {duration:.3f}s (expected ~3.0s)")
                            else:
                                print(f"   ✅ Timeout respected: {duration:.3f}s")
                                
                        except Exception as e:
                            duration = time.time() - start_time
                            print(f"   ❌ Exception after {duration:.3f}s: {e}")
                            
                            if duration > 5.0:
                                print(f"   🚨 BUG: Exception took {duration:.3f}s but should have been ~3.0s!")
                        
                        print("\n   📊 Timeout calls made during this test:")
                        for i, call in enumerate(timeout_calls, 1):
                            print(f"      {i}. timeout={call['timeout']}s from {call['caller']}")
                        
                        print()
                        
                        # Test 2: Direct tool call
                        print("📋 TEST 2: Direct ToolCall execution with 1s timeout")
                        print("   Expected: Should timeout after 1s")
                        print("   Actual behavior:")
                        
                        timeout_calls.clear()
                        
                        call = ToolCall(
                            tool="hanging_tool",
                            namespace="mcp",
                            arguments={"message": "direct test"}
                        )
                        
                        start_time = time.time()
                        try:
                            results = await processor.execute([call], timeout=1.0)
                            duration = time.time() - start_time
                            result = results[0]
                            
                            print(f"   📈 Total duration: {duration:.3f}s")
                            print(f"   📝 Result: {result.result if not result.error else f'ERROR: {result.error}'}")
                            
                            if duration > 3.0:
                                print(f"   🚨 MAJOR BUG: Took {duration:.3f}s but should have timed out at 1.0s!")
                            elif duration > 2.0:
                                print(f"   ⚠️  POSSIBLE BUG: Took {duration:.3f}s (expected ~1.0s)")
                            else:
                                print(f"   ✅ Timeout respected: {duration:.3f}s")
                                
                        except Exception as e:
                            duration = time.time() - start_time
                            print(f"   ❌ Exception after {duration:.3f}s: {e}")
                            
                        print("\n   📊 Timeout calls made during this test:")
                        for i, call in enumerate(timeout_calls, 1):
                            print(f"      {i}. timeout={call['timeout']}s from {call['caller']}")
                        
                        print()
                        
                        # Test 3: Stream manager direct call
                        print("📋 TEST 3: StreamManager.call_tool with timeout parameter")
                        print("   Expected: Should respect timeout if parameter exists")
                        print("   Actual behavior:")
                        
                        timeout_calls.clear()
                        
                        start_time = time.time()
                        try:
                            # Check if call_tool accepts timeout parameter
                            import inspect
                            sig = inspect.signature(stream_manager.call_tool)
                            has_timeout_param = 'timeout' in sig.parameters
                            
                            print(f"   📋 StreamManager.call_tool has timeout parameter: {has_timeout_param}")
                            
                            if has_timeout_param:
                                result = await stream_manager.call_tool(
                                    "hanging_tool", 
                                    {"message": "stream manager test"},
                                    timeout=2.0
                                )
                            else:
                                print("   ⚠️  No timeout parameter available!")
                                result = await stream_manager.call_tool(
                                    "hanging_tool", 
                                    {"message": "stream manager test"}
                                )
                            
                            duration = time.time() - start_time
                            print(f"   📈 Total duration: {duration:.3f}s")
                            print(f"   📝 Result: {result}")
                            
                            if has_timeout_param and duration > 4.0:
                                print(f"   🚨 BUG: Took {duration:.3f}s but should have timed out at 2.0s!")
                            elif duration > 25.0:
                                print(f"   ⚠️  Tool completed after hanging for {duration:.3f}s")
                            else:
                                print(f"   ℹ️  Completed in {duration:.3f}s")
                                
                        except Exception as e:
                            duration = time.time() - start_time
                            print(f"   ❌ Exception after {duration:.3f}s: {e}")
                        
                        print("\n   📊 Timeout calls made during this test:")
                        for i, call in enumerate(timeout_calls, 1):
                            print(f"      {i}. timeout={call['timeout']}s from {call['caller']}")
                        
                        print()
                        
                        # Summary
                        print("=== TIMEOUT ANALYSIS SUMMARY ===")
                        print("Issues to look for:")
                        print("1. wait_for calls with timeout values that don't match configured timeouts")
                        print("2. Missing timeout parameters in key methods")
                        print("3. Hardcoded timeout values instead of using configuration")
                        print("4. Timeout values that are much larger than expected (10s, 30s)")
                        
                        # Show all unique timeout values used
                        all_timeouts = [call['timeout'] for call in timeout_calls if call['timeout'] is not None]
                        unique_timeouts = sorted(set(all_timeouts))
                        print(f"\n📊 All timeout values used: {unique_timeouts}")
                        
                        # Flag suspicious timeouts
                        suspicious = [t for t in unique_timeouts if t >= 10.0]
                        if suspicious:
                            print(f"🚨 Suspicious large timeouts: {suspicious}")
                            print("   These may be hardcoded values that ignore user configuration!")
                        
                        await stream_manager.close()

if __name__ == "__main__":
    asyncio.run(test_mcp_timeout_bug()) 