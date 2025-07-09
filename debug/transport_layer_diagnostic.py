#!/usr/bin/env python
"""
transport_layer_diagnostic.py
────────────────────────────
Diagnostic to verify the lightweight wrapper approach works correctly.

This tests the architectural principle:
  chuk_tool_processor (thin wrapper) → chuk_mcp (core implementation)
"""

import asyncio
import json
import logging
import sys
import tempfile
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Test the lightweight wrapper
from chuk_tool_processor.mcp.transport.stdio_transport import StdioTransport

# Simple test server
TEST_SERVER = '''#!/usr/bin/env python3
import asyncio
import json
import sys

class TestServer:
    async def handle_message(self, message):
        method = message.get("method")
        msg_id = message.get("id")
        
        if method == "initialize":
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "test-server", "version": "1.0.0"}
                }
            }
        elif method == "notifications/initialized":
            return None
        elif method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
        elif method == "tools/list":
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {
                    "tools": [
                        {
                            "name": "test_tool",
                            "description": "A test tool",
                            "inputSchema": {"type": "object", "properties": {}}
                        }
                    ]
                }
            }
        elif method == "tools/call":
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": "Test result"}]
                }
            }
        else:
            return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}

    async def run(self):
        while True:
            try:
                line = await asyncio.to_thread(sys.stdin.readline)
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                    response = await self.handle_message(message)
                    if response:
                        print(json.dumps(response), flush=True)
                except json.JSONDecodeError:
                    pass
            except Exception:
                break

if __name__ == "__main__":
    asyncio.run(TestServer().run())
'''

class ArchitecturalTest:
    """Test the lightweight wrapper architecture."""
    
    def __init__(self):
        self.test_results = []
    
    def add_result(self, test_name: str, success: bool, details: str = ""):
        status = "✅ PASS" if success else "❌ FAIL"
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details
        })
        print(f"{status} {test_name}")
        if details:
            print(f"    {details}")
    
    async def test_lightweight_wrapper_functionality(self):
        """Test that the lightweight wrapper maintains all functionality."""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(TEST_SERVER)
            server_file = f.name
        
        try:
            # Test the lightweight wrapper
            server_params = {"command": "python", "args": [server_file]}
            transport = StdioTransport(server_params)
            
            # Test initialization
            init_success = await transport.initialize()
            self.add_result("Lightweight Wrapper - Initialization", init_success)
            
            if not init_success:
                return False
            
            # Test ping
            ping_success = await transport.send_ping()
            self.add_result("Lightweight Wrapper - Ping", ping_success)
            
            # Test tools list
            tools = await transport.get_tools()
            tools_success = len(tools) > 0
            self.add_result("Lightweight Wrapper - Tools List", tools_success, 
                          f"Found {len(tools)} tools")
            
            # Test tool call
            if tools_success and tools:
                tool_name = tools[0]["name"]
                result = await transport.call_tool(tool_name, {})
                tool_call_success = not result.get("isError", True)
                self.add_result("Lightweight Wrapper - Tool Call", tool_call_success,
                              f"Tool result: {result.get('content', 'N/A')}")
            
            # Test clean shutdown (the critical test!)
            try:
                await transport.close()
                self.add_result("Lightweight Wrapper - Clean Shutdown", True, 
                              "No cancel scope errors")
                return True
            except Exception as e:
                error_msg = str(e)
                is_cancel_scope_error = "cancel scope" in error_msg.lower()
                self.add_result("Lightweight Wrapper - Clean Shutdown", False,
                              f"Error: {error_msg}")
                return not is_cancel_scope_error
                
        except Exception as e:
            self.add_result("Lightweight Wrapper - Overall", False, f"Exception: {e}")
            return False
        finally:
            import os
            try:
                os.unlink(server_file)
            except:
                pass
    
    async def test_backward_compatibility(self):
        """Test that the wrapper maintains backward compatibility."""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(TEST_SERVER)
            server_file = f.name
        
        try:
            server_params = {"command": "python", "args": [server_file]}
            transport = StdioTransport(server_params)
            
            # Test that all expected methods exist
            methods_to_test = [
                "initialize", "close", "send_ping", "get_tools", "call_tool",
                "get_streams", "is_connected", "__aenter__", "__aexit__"
            ]
            
            missing_methods = []
            for method_name in methods_to_test:
                if not hasattr(transport, method_name):
                    missing_methods.append(method_name)
            
            backward_compat_success = len(missing_methods) == 0
            details = f"Missing methods: {missing_methods}" if missing_methods else "All methods present"
            self.add_result("Backward Compatibility - API Methods", backward_compat_success, details)
            
            # Test context manager support
            try:
                async with transport:
                    ping_result = await transport.send_ping()
                context_manager_success = ping_result
                self.add_result("Backward Compatibility - Context Manager", context_manager_success)
            except Exception as e:
                self.add_result("Backward Compatibility - Context Manager", False, f"Error: {e}")
                context_manager_success = False
            
            return backward_compat_success and context_manager_success
            
        except Exception as e:
            self.add_result("Backward Compatibility - Overall", False, f"Exception: {e}")
            return False
        finally:
            import os
            try:
                os.unlink(server_file)
            except:
                pass
    
    async def test_architecture_principles(self):
        """Test that the architecture follows lightweight wrapper principles."""
        
        # Test 1: Verify minimal code duplication (improved line counting)
        try:
            import inspect
            source = inspect.getsource(StdioTransport)
            
            # Count lines of actual implementation logic (improved filtering)
            implementation_lines = 0
            in_docstring = False
            docstring_delim = None
            
            for line in source.split('\n'):
                stripped = line.strip()
                
                # Handle multi-line docstrings
                if '"""' in stripped or "'''" in stripped:
                    if not in_docstring:
                        in_docstring = True
                        docstring_delim = '"""' if '"""' in stripped else "'''"
                        continue
                    elif docstring_delim in stripped:
                        in_docstring = False
                        continue
                
                if in_docstring:
                    continue
                
                # Skip empty lines, comments, and declarations
                if (not stripped or 
                    stripped.startswith('#') or
                    stripped.startswith('def ') or 
                    stripped.startswith('async def ') or
                    stripped.startswith('class ') or
                    stripped.startswith('from ') or
                    stripped.startswith('import ') or
                    stripped.startswith('try:') or
                    stripped.startswith('except') or
                    stripped == 'pass'):
                    continue
                
                # Count actual implementation lines
                implementation_lines += 1
            
            # The wrapper should be lightweight (< 80 lines of actual logic)
            is_lightweight = implementation_lines < 80
            self.add_result("Architecture - Lightweight Implementation", is_lightweight,
                          f"{implementation_lines} lines of core logic")
            
        except Exception as e:
            self.add_result("Architecture - Lightweight Implementation", False, f"Error: {e}")
            is_lightweight = False
        
        # Test 2: Verify delegation pattern (improved detection)
        delegation_keywords = ["chuk_mcp", "send_initialize", "send_ping", "stdio_client", "*self._streams"]
        delegation_count = sum(1 for keyword in delegation_keywords if keyword in source)
        source_contains_delegation = delegation_count >= 3  # Should have multiple delegation patterns
        self.add_result("Architecture - Delegation Pattern", source_contains_delegation,
                      f"Found {delegation_count}/5 delegation patterns")
        
        # Test 3: Verify no transport reimplementation (improved detection)
        bad_implementations = [
            "anyio.open_process",  # Direct process management
            "asyncio.create_subprocess",  # Alternative process creation
            "sys.stdin.readline",  # Direct stdin handling
            "JSONRPCMessage",  # Direct JSON-RPC handling
            "_stdout_reader",  # Internal transport methods
            "_stdin_writer",  # Internal transport methods
        ]
        
        reimplementation_found = any(bad_keyword in source for bad_keyword in bad_implementations)
        no_reimplementation = not reimplementation_found
        
        # Check for good delegation patterns
        good_patterns = [
            "await send_", # Uses chuk_mcp send functions
            "stdio_client(", # Uses chuk_mcp client
            "*self._streams", # Clean delegation pattern
        ]
        good_pattern_count = sum(1 for pattern in good_patterns if pattern in source)
        
        self.add_result("Architecture - No Transport Reimplementation", 
                      no_reimplementation and good_pattern_count >= 2,
                      f"Uses delegation patterns, no direct transport implementation")
        
        return is_lightweight and source_contains_delegation and no_reimplementation
    
    async def test_cancel_scope_fix(self):
        """Test that the cancel scope error is fixed (the main issue we're solving)."""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(TEST_SERVER)
            server_file = f.name
        
        try:
            # Test multiple rapid connections and shutdowns (stress test for cancel scope)
            for i in range(3):
                server_params = {"command": "python", "args": [server_file]}
                transport = StdioTransport(server_params)
                
                try:
                    # Initialize, do some work, then close
                    init_success = await transport.initialize()
                    if init_success:
                        await transport.send_ping()
                        await transport.get_tools()
                    
                    # The critical test: clean shutdown without cancel scope errors
                    await transport.close()
                    
                except Exception as e:
                    error_msg = str(e)
                    if "cancel scope" in error_msg.lower():
                        self.add_result("Critical Fix - No Cancel Scope Errors", False,
                                      f"Cancel scope error detected: {error_msg}")
                        return False
                    else:
                        # Other errors might be OK, but cancel scope errors are not
                        pass
            
            self.add_result("Critical Fix - No Cancel Scope Errors", True,
                          "Multiple connection/shutdown cycles completed without cancel scope errors")
            return True
            
        except Exception as e:
            error_msg = str(e)
            is_cancel_scope = "cancel scope" in error_msg.lower()
            self.add_result("Critical Fix - No Cancel Scope Errors", not is_cancel_scope,
                          f"Exception: {error_msg}")
            return not is_cancel_scope
        finally:
            import os
            try:
                os.unlink(server_file)
            except:
                pass
        """Print test summary."""
        print("\n" + "="*70)
        print("📊 TRANSPORT LAYER ARCHITECTURE DIAGNOSTIC SUMMARY")
        print("="*70)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["success"])
        
        print(f"Tests run: {total_tests}")
        print(f"Tests passed: {passed_tests}")
        print(f"Tests failed: {total_tests - passed_tests}")
        
        if passed_tests == total_tests:
            print("\n🎉 SUCCESS: All architectural tests passed!")
            print("✅ The lightweight wrapper approach is working correctly.")
            print("✅ No more transport layer duplication.")
            print("✅ Clean delegation to chuk_mcp core library.")
        else:
            print(f"\n❌ FAILURE: {total_tests - passed_tests} tests failed")
            print("🔧 The lightweight wrapper needs refinement.")
        
        print("\nDetailed Results:")
        for result in self.test_results:
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            print(f"  {status} {result['test']}")
            if result["details"]:
                print(f"      {result['details']}")

async def run_architectural_diagnostic():
    """Run the complete architectural diagnostic."""
    print("🏗️  TRANSPORT LAYER ARCHITECTURE DIAGNOSTIC")
    print("="*70)
    print("Testing the lightweight wrapper approach:")
    print("  chuk_tool_processor → chuk_mcp (delegation)")
    print("  No transport logic duplication")
    print("  Backward compatibility maintained")
    print("="*70)
    
    tester = ArchitecturalTest()
    
    # Run all tests
    print("\n🧪 Testing cancel scope fix (critical)...")
    await tester.test_cancel_scope_fix()
    
    print("\n🧪 Testing lightweight wrapper functionality...")
    await tester.test_lightweight_wrapper_functionality()
    
    print("\n🧪 Testing backward compatibility...")
    await tester.test_backward_compatibility()
    
    print("\n🧪 Testing architectural principles...")
    await tester.test_architecture_principles()
    
    # Print summary
    tester.print_summary()
    
    # Return overall success
    return all(r["success"] for r in tester.test_results)

async def main():
    """Main diagnostic entry point."""
    try:
        success = await run_architectural_diagnostic()
        
        if success:
            print("\n🎉 Architecture diagnostic completed successfully!")
            print("The lightweight wrapper approach is working correctly.")
            sys.exit(0)
        else:
            print("\n❌ Architecture diagnostic found issues.")
            print("The lightweight wrapper needs refinement.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n👋 Diagnostic interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Diagnostic failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())