#!/usr/bin/env python
# examples/find_hardcoded_timeout.py
"""
Find the exact location of hardcoded timeout values causing the bug.
"""

import re
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def search_for_hardcoded_timeouts():
    """Search for hardcoded timeout values in the codebase."""

    print("=== SEARCHING FOR HARDCODED TIMEOUT VALUES ===\n")

    # Files to search
    search_files = [
        "chuk_tool_processor/execution/strategies/inprocess_strategy.py",
        "chuk_tool_processor/mcp/stream_manager.py",
        "chuk_tool_processor/mcp/transport/sse_transport.py",
        "chuk_tool_processor/mcp/mcp_tool.py",
        "chuk_tool_processor/execution/tool_executor.py",
    ]

    # Patterns to look for
    timeout_patterns = [
        r"timeout=(\d+\.?\d*)",  # timeout=10.0
        r"wait_for\([^,]+,\s*(\d+\.?\d*)",  # wait_for(coro, 10.0)
        r"DEFAULT_TIMEOUT\s*=\s*(\d+\.?\d*)",  # DEFAULT_TIMEOUT = 30.0
        r"(\d+\.?\d*)\s*#.*timeout",  # 10.0 # timeout comment
    ]

    found_issues = []

    for file_path in search_files:
        full_path = PROJECT_ROOT / file_path

        if not full_path.exists():
            print(f"❌ File not found: {file_path}")
            continue

        print(f"🔍 Searching {file_path}:")

        try:
            with open(full_path) as f:
                lines = f.readlines()

            file_issues = []

            for line_num, line in enumerate(lines, 1):
                for pattern in timeout_patterns:
                    matches = re.finditer(pattern, line)
                    for match in matches:
                        timeout_value = float(match.group(1))

                        # Flag suspicious timeout values
                        if timeout_value >= 10.0:
                            issue = {
                                "file": file_path,
                                "line": line_num,
                                "content": line.strip(),
                                "timeout": timeout_value,
                                "severity": "HIGH" if timeout_value == 10.0 else "MEDIUM",
                            }
                            file_issues.append(issue)
                            found_issues.append(issue)

                            severity_emoji = "🚨" if timeout_value == 10.0 else "⚠️"
                            print(f"   {severity_emoji} Line {line_num}: {line.strip()}")
                            print(f"      -> Found timeout value: {timeout_value}s")

            if not file_issues:
                print("   ✅ No suspicious hardcoded timeouts found")

        except Exception as e:
            print(f"   ❌ Error reading file: {e}")

        print()

    return found_issues


def search_wait_for_calls():
    """Search specifically for asyncio.wait_for calls."""

    print("=== SEARCHING FOR ASYNCIO.WAIT_FOR CALLS ===\n")

    search_dirs = ["chuk_tool_processor/execution", "chuk_tool_processor/mcp"]

    wait_for_pattern = r"(await\s+)?asyncio\.wait_for\s*\([^)]+\)"

    for search_dir in search_dirs:
        dir_path = PROJECT_ROOT / search_dir

        if not dir_path.exists():
            continue

        print(f"🔍 Searching directory: {search_dir}")

        for py_file in dir_path.rglob("*.py"):
            relative_path = py_file.relative_to(PROJECT_ROOT)

            try:
                with open(py_file) as f:
                    content = f.read()
                    lines = content.split("\n")

                matches = list(re.finditer(wait_for_pattern, content, re.DOTALL))

                if matches:
                    print(f"   📁 {relative_path}:")

                    for match in matches:
                        # Find which line this match is on
                        start_pos = match.start()
                        line_num = content[:start_pos].count("\n") + 1

                        # Get the full line for context
                        if line_num <= len(lines):
                            line_content = lines[line_num - 1].strip()
                            print(f"      Line {line_num}: {line_content}")

                            # Check if this line contains hardcoded timeout
                            if any(val in line_content for val in ["10.0", "30.0", "60.0"]):
                                print("         🚨 POTENTIAL ISSUE: Contains hardcoded timeout!")
                    print()

            except Exception as e:
                print(f"   ❌ Error reading {relative_path}: {e}")


def check_current_runtime_behavior():
    """Check what's actually happening at runtime."""

    print("=== RUNTIME INSPECTION ===\n")

    try:
        # Import and inspect the actual strategy
        import inspect

        from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy

        print("🔍 Inspecting InProcessStrategy._run_with_timeout:")

        # Get the source code of the method
        method = InProcessStrategy._run_with_timeout
        source = inspect.getsource(method)

        print("📋 Method source code:")
        lines = source.split("\n")
        for i, line in enumerate(lines, 1):
            if "wait_for" in line:
                print(f"   Line {i}: {line}")
                if "10.0" in line or "30.0" in line:
                    print("      🚨 FOUND HARDCODED TIMEOUT!")
            elif "timeout" in line and ("=" in line or "await" in line):
                print(f"   Line {i}: {line}")

        print()

        # Check method signature
        sig = inspect.signature(method)
        print(f"🔍 Method signature: {method.__name__}{sig}")

        # Check for parameter defaults
        for param_name, param in sig.parameters.items():
            if "timeout" in param_name.lower():
                print(f"   Parameter '{param_name}': {param}")
                if param.default != inspect.Parameter.empty:
                    print(f"      Default value: {param.default}")
                    if isinstance(param.default, int | float) and param.default >= 10:
                        print(f"      🚨 SUSPICIOUS DEFAULT: {param.default}")

    except Exception as e:
        print(f"❌ Error during runtime inspection: {e}")


def find_actual_line_533():
    """Find what's actually on line 533 of inprocess_strategy.py."""

    print("=== INSPECTING LINE 533 ===\n")

    strategy_file = PROJECT_ROOT / "chuk_tool_processor/execution/strategies/inprocess_strategy.py"

    if not strategy_file.exists():
        print("❌ inprocess_strategy.py not found")
        return

    try:
        with open(strategy_file) as f:
            lines = f.readlines()

        if len(lines) >= 533:
            line_533 = lines[532].strip()  # Line 533 (0-indexed)
            print(f"📍 Line 533: {line_533}")

            # Check surrounding lines for context
            start_line = max(0, 530)
            end_line = min(len(lines), 536)

            print(f"\n🔍 Context around line 533 (lines {start_line + 1}-{end_line}):")
            for i in range(start_line, end_line):
                line_num = i + 1
                line_content = lines[i].rstrip()
                marker = " >>> " if line_num == 533 else "     "
                print(f"{marker}{line_num:3d}: {line_content}")

                if "wait_for" in line_content and ("10.0" in line_content or "30.0" in line_content):
                    print(f"          🚨 FOUND HARDCODED TIMEOUT ON LINE {line_num}!")
        else:
            print(f"❌ File only has {len(lines)} lines, but error mentioned line 533")

    except Exception as e:
        print(f"❌ Error reading file: {e}")


if __name__ == "__main__":
    print("🔍 HUNTING FOR THE HARDCODED TIMEOUT BUG\n")

    # Run all searches
    issues = search_for_hardcoded_timeouts()
    search_wait_for_calls()
    find_actual_line_533()
    check_current_runtime_behavior()

    # Summary
    print("=" * 60)
    print("🎯 SUMMARY")
    print("=" * 60)

    if issues:
        print(f"🚨 Found {len(issues)} potential timeout issues:")
        for issue in issues:
            severity_emoji = "🚨" if issue["severity"] == "HIGH" else "⚠️"
            print(f"   {severity_emoji} {issue['file']}:{issue['line']} - {issue['timeout']}s timeout")
    else:
        print("❓ No obvious hardcoded timeouts found in static analysis.")
        print("The bug might be:")
        print("   1. In a different file not searched")
        print("   2. In compiled bytecode vs source mismatch")
        print("   3. A runtime issue with parameter passing")
        print("   4. In imported modules/dependencies")

    print("\n🔧 Next steps:")
    print("1. Check if you have multiple versions of the code")
    print("2. Verify you're running the code you think you are")
    print("3. Look for the actual line 533 mentioned in the error")
    print("4. Check if there are cached .pyc files with old code")
