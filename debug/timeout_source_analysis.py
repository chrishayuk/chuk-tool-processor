#!/usr/bin/env python
# examples/timeout_source_analysis.py
"""
Analyze the source code to find where timeout values are being set incorrectly.
"""

import asyncio
import sys
import inspect
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.mcp.stream_manager import StreamManager
from chuk_tool_processor.mcp.transport.sse_transport import SSETransport
from chuk_tool_processor.mcp.mcp_tool import MCPTool

def analyze_timeout_sources():
    """Analyze source code to find hardcoded timeout values."""
    
    print("=== TIMEOUT SOURCE CODE ANALYSIS ===\n")
    
    # Analyze InProcessStrategy
    print("📋 1. InProcessStrategy Analysis")
    print("=" * 40)
    
    strategy_source = inspect.getsource(InProcessStrategy)
    
    # Look for timeout-related patterns
    timeout_patterns = [
        "timeout=",
        "default_timeout",
        "wait_for(",
        "10.0",
        "30.0"
    ]
    
    print("🔍 Searching for timeout patterns in InProcessStrategy:")
    for pattern in timeout_patterns:
        if pattern in strategy_source:
            lines = strategy_source.split('\n')
            matching_lines = [
                (i+1, line.strip()) for i, line in enumerate(lines) 
                if pattern in line and not line.strip().startswith('#')
            ]
            if matching_lines:
                print(f"   Pattern '{pattern}' found:")
                for line_num, line in matching_lines[:3]:  # Show first 3 matches
                    print(f"     Line {line_num}: {line}")
                if len(matching_lines) > 3:
                    print(f"     ... and {len(matching_lines) - 3} more")
                print()
    
    # Check specific method signatures
    print("🔍 Method signature analysis:")
    
    methods_to_check = [
        '_execute_single_call',
        '_run_with_timeout', 
        'run',
        'stream_run'
    ]
    
    for method_name in methods_to_check:
        if hasattr(InProcessStrategy, method_name):
            method = getattr(InProcessStrategy, method_name)
            sig = inspect.signature(method)
            print(f"   {method_name}{sig}")
            
            # Check if method has timeout parameter with default value
            if 'timeout' in sig.parameters:
                timeout_param = sig.parameters['timeout']
                print(f"     -> timeout parameter: {timeout_param}")
            else:
                print(f"     -> ❌ No timeout parameter")
        else:
            print(f"   ❌ Method {method_name} not found")
    
    print()
    
    # Analyze StreamManager
    print("📋 2. StreamManager Analysis")
    print("=" * 40)
    
    manager_source = inspect.getsource(StreamManager)
    
    print("🔍 Searching for timeout patterns in StreamManager:")
    for pattern in timeout_patterns:
        if pattern in manager_source:
            lines = manager_source.split('\n')
            matching_lines = [
                (i+1, line.strip()) for i, line in enumerate(lines) 
                if pattern in line and not line.strip().startswith('#')
            ]
            if matching_lines:
                print(f"   Pattern '{pattern}' found:")
                for line_num, line in matching_lines[:3]:
                    print(f"     Line {line_num}: {line}")
                if len(matching_lines) > 3:
                    print(f"     ... and {len(matching_lines) - 3} more")
                print()
    
    # Check StreamManager.call_tool signature
    if hasattr(StreamManager, 'call_tool'):
        sig = inspect.signature(StreamManager.call_tool)
        print(f"🔍 StreamManager.call_tool{sig}")
        if 'timeout' in sig.parameters:
            timeout_param = sig.parameters['timeout']
            print(f"   -> timeout parameter: {timeout_param}")
        else:
            print(f"   -> ❌ No timeout parameter in call_tool")
    
    print()
    
    # Analyze SSETransport
    print("📋 3. SSETransport Analysis")
    print("=" * 40)
    
    transport_source = inspect.getsource(SSETransport)
    
    print("🔍 Searching for hardcoded timeout values in SSETransport:")
    hardcoded_timeouts = ["10.0", "30.0", "DEFAULT_TIMEOUT"]
    
    for pattern in hardcoded_timeouts:
        if pattern in transport_source:
            lines = transport_source.split('\n')
            matching_lines = [
                (i+1, line.strip()) for i, line in enumerate(lines) 
                if pattern in line and not line.strip().startswith('#')
            ]
            if matching_lines:
                print(f"   🚨 HARDCODED VALUE '{pattern}' found:")
                for line_num, line in matching_lines:
                    print(f"     Line {line_num}: {line}")
                print()
    
    # Check if DEFAULT_TIMEOUT is defined
    if hasattr(SSETransport, '__module__'):
        module = sys.modules[SSETransport.__module__]
        if hasattr(module, 'DEFAULT_TIMEOUT'):
            default_timeout = getattr(module, 'DEFAULT_TIMEOUT')
            print(f"🔍 Found DEFAULT_TIMEOUT = {default_timeout}")
        else:
            print("ℹ️  No DEFAULT_TIMEOUT module constant found")
    
    print()
    
    # Analyze MCPTool
    print("📋 4. MCPTool Analysis")  
    print("=" * 40)
    
    if hasattr(MCPTool, '__init__'):
        init_sig = inspect.signature(MCPTool.__init__)
        print(f"🔍 MCPTool.__init__{init_sig}")
        
        if 'default_timeout' in init_sig.parameters:
            timeout_param = init_sig.parameters['default_timeout']
            print(f"   -> default_timeout parameter: {timeout_param}")
        else:
            print(f"   -> ❌ No default_timeout parameter")
    
    if hasattr(MCPTool, 'execute'):
        execute_sig = inspect.signature(MCPTool.execute)
        print(f"🔍 MCPTool.execute{execute_sig}")
        
        if 'timeout' in execute_sig.parameters:
            timeout_param = execute_sig.parameters['timeout']
            print(f"   -> timeout parameter: {timeout_param}")
        else:
            print(f"   -> ❌ No timeout parameter in execute")
    
    mcp_source = inspect.getsource(MCPTool)
    
    print("🔍 Looking for timeout handling in MCPTool:")
    if "default_timeout" in mcp_source:
        lines = mcp_source.split('\n')
        matching_lines = [
            (i+1, line.strip()) for i, line in enumerate(lines) 
            if "default_timeout" in line or "timeout" in line
        ]
        for line_num, line in matching_lines[:5]:
            print(f"   Line {line_num}: {line}")
    
    print()
    
    # Summary of findings
    print("📋 5. SUMMARY OF FINDINGS")
    print("=" * 40)
    
    issues = []
    
    # Check if InProcessStrategy respects