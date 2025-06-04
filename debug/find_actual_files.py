#!/usr/bin/env python
# examples/find_actual_files.py
"""
Find the actual file structure and locate where the hardcoded timeout bug is.
"""

import os
import sys
import inspect
from pathlib import Path

def find_project_structure():
    """Find the actual project structure."""
    
    print("=== FINDING PROJECT STRUCTURE ===\n")
    
    # Start from current directory and work up
    current_dir = Path.cwd()
    print(f"📍 Current directory: {current_dir}")
    
    # Look for Python files that might contain our code
    python_files = list(current_dir.rglob("*.py"))
    
    # Filter for files related to chuk_tool_processor
    chuk_files = [f for f in python_files if "chuk" in str(f).lower() or "tool" in str(f).lower()]
    
    if chuk_files:
        print(f"🔍 Found {len(chuk_files)} chuk/tool-related Python files:")
        for f in chuk_files[:20]:  # Show first 20
            relative = f.relative_to(current_dir)
            print(f"   {relative}")
        if len(chuk_files) > 20:
            print(f"   ... and {len(chuk_files) - 20} more")
    else:
        print("❌ No chuk-related Python files found")
    
    print()
    
    # Look specifically for inprocess_strategy.py
    strategy_files = list(current_dir.rglob("*inprocess_strategy*.py"))
    
    print(f"🎯 InProcess Strategy files found: {len(strategy_files)}")
    for f in strategy_files:
        relative = f.relative_to(current_dir)
        print(f"   📁 {relative}")
        
        # Check if this file has the _run_with_timeout method
        try:
            with open(f, 'r') as file:
                content = file.read()
                if '_run_with_timeout' in content:
                    print(f"      ✅ Contains _run_with_timeout method")
                    
                    # Look for wait_for calls
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        if 'asyncio.wait_for' in line and ('10.0' in line or '30.0' in line):
                            print(f"      🚨 Line {i}: {line.strip()}")
                            print(f"         ^^^ FOUND HARDCODED TIMEOUT!")
                        elif 'wait_for' in line and 'timeout' in line:
                            print(f"      📍 Line {i}: {line.strip()}")
                else:
                    print(f"      ❌ Does not contain _run_with_timeout method")
        except Exception as e:
            print(f"      ❌ Error reading file: {e}")
    
    print()
    return strategy_files

def find_imported_module_location():
    """Find where Python is actually importing the module from."""
    
    print("=== FINDING IMPORTED MODULE LOCATION ===\n")
    
    try:
        # Import the module and find its actual location
        from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
        
        module_file = inspect.getfile(InProcessStrategy)
        print(f"📍 InProcessStrategy imported from: {module_file}")
        
        # Check if this file exists and inspect it
        file_path = Path(module_file)
        if file_path.exists():
            print(f"✅ File exists at: {file_path}")
            
            # Read the actual imported file
            with open(file_path, 'r') as f:
                content = f.read()
                lines = content.split('\n')
                
            print(f"📄 File has {len(lines)} lines")
            
            # Check line 533 specifically (since error mentioned it)
            if len(lines) >= 533:
                line_533 = lines[532]  # 0-indexed
                print(f"📍 Line 533: {line_533}")
                
                if 'wait_for' in line_533:
                    if '10.0' in line_533:
                        print(f"🚨 FOUND THE BUG! Line 533 has hardcoded 10.0 timeout:")
                        print(f"   {line_533.strip()}")
                    else:
                        print(f"ℹ️  Line 533 has wait_for but no obvious hardcoded timeout")
                
                # Show context around line 533
                start = max(0, 530)
                end = min(len(lines), 540)
                print(f"\n🔍 Context around line 533 (lines {start+1}-{end}):")
                for i in range(start, end):
                    line_num = i + 1
                    line = lines[i]
                    marker = ">>> " if line_num == 533 else "    "
                    print(f"{marker}{line_num:3d}: {line}")
                    
                    if 'wait_for' in line and ('10.0' in line or '30.0' in line):
                        print(f"         🚨 HARDCODED TIMEOUT FOUND ON LINE {line_num}!")
            else:
                print(f"❌ File only has {len(lines)} lines, but error mentioned line 533")
                
            # Search entire file for hardcoded timeouts
            print(f"\n🔍 Searching entire file for hardcoded timeouts:")
            found_hardcoded = False
            for i, line in enumerate(lines, 1):
                if 'wait_for' in line and ('10.0' in line or '30.0' in line):
                    print(f"   🚨 Line {i}: {line.strip()}")
                    found_hardcoded = True
                    
            if not found_hardcoded:
                print("   ✅ No hardcoded timeouts found in wait_for calls")
                
        else:
            print(f"❌ File does not exist at: {file_path}")
            
    except ImportError as e:
        print(f"❌ Could not import InProcessStrategy: {e}")
    except Exception as e:
        print(f"❌ Error inspecting imported module: {e}")
        import traceback
        traceback.print_exc()

def check_sys_path_and_imports():
    """Check sys.path and import resolution."""
    
    print("\n=== CHECKING IMPORT RESOLUTION ===\n")
    
    print("📍 Python sys.path:")
    for i, path in enumerate(sys.path):
        print(f"   {i}: {path}")
        
        # Check if this path contains chuk_tool_processor
        path_obj = Path(path)
        if path_obj.exists():
            chuk_path = path_obj / "chuk_tool_processor"
            if chuk_path.exists():
                print(f"      ✅ Contains chuk_tool_processor/")
                
                strategy_path = chuk_path / "execution" / "strategies" / "inprocess_strategy.py"
                if strategy_path.exists():
                    print(f"         ✅ Contains inprocess_strategy.py")
                    
                    # This is probably where the import is coming from
                    print(f"         📍 Full path: {strategy_path}")
                    
                    # Check this specific file for hardcoded timeouts
                    try:
                        with open(strategy_path, 'r') as f:
                            content = f.read()
                            
                        lines = content.split('\n')
                        print(f"         📄 File has {len(lines)} lines")
                        
                        # Check for hardcoded timeouts
                        hardcoded_found = []
                        for line_num, line in enumerate(lines, 1):
                            if 'wait_for' in line and ('10.0' in line or '30.0' in line):
                                hardcoded_found.append((line_num, line.strip()))
                                
                        if hardcoded_found:
                            print(f"         🚨 FOUND {len(hardcoded_found)} HARDCODED TIMEOUTS:")
                            for line_num, line in hardcoded_found:
                                print(f"            Line {line_num}: {line}")
                        else:
                            print(f"         ✅ No hardcoded timeouts found")
                            
                    except Exception as e:
                        print(f"         ❌ Error reading file: {e}")

def search_all_python_files():
    """Search all Python files for hardcoded 10.0 timeouts."""
    
    print("\n=== SEARCHING ALL PYTHON FILES ===\n")
    
    current_dir = Path.cwd()
    all_py_files = list(current_dir.rglob("*.py"))
    
    print(f"🔍 Searching {len(all_py_files)} Python files for 'wait_for' + '10.0'...")
    
    matches = []
    for py_file in all_py_files:
        try:
            with open(py_file, 'r') as f:
                content = f.read()
                lines = content.split('\n')
                
            for line_num, line in enumerate(lines, 1):
                if 'wait_for' in line and '10.0' in line:
                    relative_path = py_file.relative_to(current_dir)
                    matches.append((relative_path, line_num, line.strip()))
                    
        except Exception:
            continue  # Skip files that can't be read
            
    if matches:
        print(f"🚨 FOUND {len(matches)} FILES WITH HARDCODED 10.0 TIMEOUTS:")
        for file_path, line_num, line in matches:
            print(f"   📁 {file_path}:{line_num}")
            print(f"      {line}")
    else:
        print("✅ No files found with hardcoded 10.0 timeouts in wait_for calls")

if __name__ == "__main__":
    print("🔍 FINDING ACTUAL FILE LOCATIONS AND TIMEOUT BUGS\n")
    
    strategy_files = find_project_structure()
    find_imported_module_location()
    check_sys_path_and_imports()
    search_all_python_files()
    
    print("\n" + "="*60)
    print("🎯 SUMMARY")
    print("="*60)
    print("Look for '🚨 FOUND THE BUG!' or '🚨 HARDCODED TIMEOUT FOUND' messages above.")
    print("These will show you exactly which file and line has the hardcoded 10.0 timeout.")
    
    if strategy_files:
        print(f"\nStrategy files found: {len(strategy_files)}")
        print("Check each one for the hardcoded timeout bug.")
    else:
        print("\nNo strategy files found - the issue might be in a different location.")
        
    print("\n🔧 After finding the bug:")
    print("1. Edit the file with hardcoded timeout")
    print("2. Change 'timeout=10.0' to 'timeout=timeout'")  
    print("3. Clear any .pyc cache files")
    print("4. Re-run your timeout test to verify the fix")