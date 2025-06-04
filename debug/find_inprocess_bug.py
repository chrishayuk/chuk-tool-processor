#!/usr/bin/env python
# examples/find_inprocess_bug.py
"""
Find the exact hardcoded timeout bug in InProcessStrategy.
"""

import asyncio
import sys
import inspect
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

def find_inprocess_strategy_file():
    """Find the actual InProcessStrategy file being used."""
    
    print("=== FINDING INPROCESS STRATEGY BUG ===\n")
    
    try:
        # Import and get the actual file location
        from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
        
        module_file = inspect.getfile(InProcessStrategy)
        print(f"📍 InProcessStrategy loaded from: {module_file}")
        
        # Read the actual file
        with open(module_file, 'r') as f:
            content = f.read()
            lines = content.split('\n')
        
        print(f"📄 File has {len(lines)} lines")
        
        # Find line 533 specifically
        if len(lines) >= 533:
            line_533 = lines[532]  # 0-indexed
            print(f"\n📍 Line 533: {line_533}")
            
            if 'wait_for' in line_533 and '10.0' in line_533:
                print(f"🚨 FOUND THE BUG! Line 533 has hardcoded 10.0:")
                print(f"   {line_533.strip()}")
            elif 'wait_for' in line_533:
                print(f"ℹ️  Line 533 has wait_for but uses variable timeout")
                print(f"   Need to check what 'timeout' variable contains")
        
        # Search for all hardcoded timeouts in the file
        print(f"\n🔍 Searching entire file for hardcoded timeouts:")
        hardcoded_found = []
        
        for line_num, line in enumerate(lines, 1):
            # Look for wait_for with hardcoded values
            if 'wait_for' in line and ('10.0' in line or '30.0' in line):
                hardcoded_found.append((line_num, line.strip()))
                
            # Also look for timeout assignments
            elif 'timeout' in line and ('= 10.0' in line or '= 30.0' in line):
                hardcoded_found.append((line_num, line.strip()))
        
        if hardcoded_found:
            print(f"🚨 FOUND {len(hardcoded_found)} HARDCODED TIMEOUTS:")
            for line_num, line in hardcoded_found:
                print(f"   Line {line_num}: {line}")
        else:
            print("✅ No obvious hardcoded timeouts found")
            
        # Look for the _run_with_timeout method specifically
        print(f"\n🔍 Analyzing _run_with_timeout method:")
        
        method = InProcessStrategy._run_with_timeout
        source = inspect.getsource(method)
        method_lines = source.split('\n')
        
        for i, line in enumerate(method_lines, 1):
            if 'wait_for' in line:
                print(f"   Line {i}: {line.strip()}")
                if '10.0' in line or '30.0' in line:
                    print(f"      🚨 HARDCODED TIMEOUT FOUND!")
                    
        # Check if there are any default parameter values
        sig = inspect.signature(method)
        print(f"\n🔍 Method signature: {method.__name__}{sig}")
        
        for param_name, param in sig.parameters.items():
            if param.default != inspect.Parameter.empty:
                print(f"   Parameter '{param_name}' default: {param.default}")
                if isinstance(param.default, (int, float)) and param.default >= 10:
                    print(f"      🚨 SUSPICIOUS DEFAULT VALUE: {param.default}")
                    
    except Exception as e:
        print(f"❌ Error analyzing InProcessStrategy: {e}")
        import traceback
        traceback.print_exc()

def check_default_timeout_flow():
    """Check how default_timeout flows through the system."""
    
    print(f"\n=== CHECKING DEFAULT TIMEOUT FLOW ===\n")
    
    try:
        from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
        from chuk_tool_processor.registry.provider import ToolRegistryProvider
        import asyncio
        
        async def trace_timeout_flow():
            registry = await ToolRegistryProvider.get_registry()
            
            # Create strategy with 2.0 timeout
            strategy = InProcessStrategy(
                registry=registry,
                default_timeout=2.0
            )
            
            print(f"✅ Created strategy with default_timeout: {strategy.default_timeout}")
            
            # Check what happens when we call _run_with_timeout
            # We need to create a mock tool call to test
            from chuk_tool_processor.models.tool_call import ToolCall
            from datetime import datetime, timezone
            import os
            
            call = ToolCall(tool="nonexistent", arguments={})
            start = datetime.now(timezone.utc)
            machine = os.uname().nodename
            pid = os.getpid()
            
            # Create a mock tool object
            class MockTool:
                async def execute(self, **kwargs):
                    await asyncio.sleep(5.0)  # Simulate long operation
                    return {"test": "result"}
            
            mock_tool = MockTool()
            
            print(f"🔍 Testing _run_with_timeout with timeout=2.0...")
            
            # Monkey patch asyncio.wait_for to see what timeout is actually used
            original_wait_for = asyncio.wait_for
            captured_timeout = None
            
            async def capture_wait_for(coro, timeout=None):
                nonlocal captured_timeout
                captured_timeout = timeout
                print(f"   📊 wait_for called with timeout={timeout}")
                # Don't actually wait, just return a mock result
                return {"mock": "result"}
            
            # Patch and test
            asyncio.wait_for = capture_wait_for
            
            try:
                result = await strategy._run_with_timeout(
                    tool=mock_tool,
                    call=call,
                    timeout=2.0,  # Explicit 2.0 timeout
                    start=start,
                    machine=machine,
                    pid=pid
                )
                
                if captured_timeout == 2.0:
                    print(f"   ✅ Correct! _run_with_timeout used timeout=2.0")
                elif captured_timeout == 10.0:
                    print(f"   🚨 BUG! _run_with_timeout used timeout=10.0 instead of 2.0")
                    print(f"      This means there's a hardcoded 10.0 in the method!")
                else:
                    print(f"   ❓ Unexpected timeout value: {captured_timeout}")
                    
            finally:
                # Restore original
                asyncio.wait_for = original_wait_for
        
        # Run the async test
        asyncio.run(trace_timeout_flow())
        
    except Exception as e:
        print(f"❌ Error tracing timeout flow: {e}")
        import traceback
        traceback.print_exc()

def check_effective_timeout_calculation():
    """Check how effective_timeout is calculated in InProcessStrategy."""
    
    print(f"\n=== CHECKING EFFECTIVE TIMEOUT CALCULATION ===\n")
    
    try:
        from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
        from chuk_tool_processor.registry.provider import ToolRegistryProvider
        import asyncio
        
        async def trace_effective_timeout():
            registry = await ToolRegistryProvider.get_registry()
            
            # Test 1: Strategy with 2.0 default, no explicit timeout
            strategy = InProcessStrategy(registry=registry, default_timeout=2.0)
            
            print(f"🔍 Strategy default_timeout: {strategy.default_timeout}")
            
            # Look at the run method to see how it calculates effective_timeout
            run_method = InProcessStrategy.run
            source = inspect.getsource(run_method)
            
            print(f"\n📋 Analyzing run() method for timeout calculation:")
            lines = source.split('\n')
            for i, line in enumerate(lines, 1):
                if 'effective_timeout' in line or 'timeout' in line.lower():
                    print(f"   Line {i}: {line.strip()}")
                    
            # Also check _execute_single_call
            exec_method = InProcessStrategy._execute_single_call  
            exec_source = inspect.getsource(exec_method)
            
            print(f"\n📋 Analyzing _execute_single_call() method:")
            exec_lines = exec_source.split('\n')
            for i, line in enumerate(exec_lines, 1):
                if 'timeout' in line.lower():
                    print(f"   Line {i}: {line.strip()}")
                    
        asyncio.run(trace_effective_timeout())
        
    except Exception as e:
        print(f"❌ Error checking effective timeout: {e}")

if __name__ == "__main__":
    print("🔍 HUNTING FOR THE INPROCESS STRATEGY BUG\n")
    
    find_inprocess_strategy_file()
    check_default_timeout_flow()
    check_effective_timeout_calculation()
    
    print("\n" + "="*60)
    print("🎯 SUMMARY")
    print("="*60)
    print("Look for '🚨 FOUND THE BUG!' messages above.")
    print("The hardcoded 10.0 timeout is definitely in InProcessStrategy,")
    print("even though we fixed the SSE transport.")
    print("\n🔧 If you found the bug:")
    print("1. Edit the file shown above")
    print("2. Change the hardcoded 10.0 to use the timeout parameter")
    print("3. Re-run the timeout test to verify the fix")