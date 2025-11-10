#!/usr/bin/env python3
"""Check that all examples use the new DX patterns."""

from pathlib import Path


def check_dx_patterns(file_path: Path) -> list[str]:
    """Check a file for DX anti-patterns."""
    issues = []

    with open(file_path) as f:
        content = f.read()

    # Check for old import patterns
    if "from chuk_tool_processor.core.processor import ToolProcessor" in content:
        issues.append("❌ Old import: should use 'from chuk_tool_processor import ToolProcessor'")

    if "from chuk_tool_processor.registry import" in content and (
        "initialize" in content or "register_tool" in content
    ):
        # Check if it's importing initialize or register_tool separately
        issues.append("❌ Old import: should use 'from chuk_tool_processor import initialize, register_tool'")

    if "SubprocessStrategy as IsolatedStrategy" in content and "from chuk_tool_processor.execution" in content:
        issues.append("❌ Old import: should use 'from chuk_tool_processor import IsolatedStrategy'")

    if "from chuk_tool_processor.execution.strategies.subprocess_strategy" in content:
        issues.append(
            "❌ Deep import: should use 'from chuk_tool_processor import SubprocessStrategy' or 'IsolatedStrategy'"
        )

    if "from chuk_tool_processor.execution.strategies.inprocess_strategy" in content:
        issues.append("❌ Deep import: should use 'from chuk_tool_processor import InProcessStrategy'")

    # Check for processor usage without context manager
    # Look for ToolProcessor() without async with
    if "processor = ToolProcessor(" in content:
        # Check if there's an async with nearby
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "processor = ToolProcessor(" in line:
                # Check previous 2 lines for async with
                found_async_with = False
                for j in range(max(0, i - 2), i):
                    if "async with" in lines[j] and "ToolProcessor" in lines[j]:
                        found_async_with = True
                        break

                if (
                    not found_async_with
                    and "async with" not in line
                    and "await processor.close()" not in content
                    and "await manager.close()" not in content
                ):
                    # This might be a pattern without context manager
                    # Only flag if we don't see await processor.close() or manager.close()
                    issues.append("⚠️  Consider: Using 'async with ToolProcessor()' for automatic cleanup")
                    break

    return issues


def main():
    examples_dir = Path("examples")

    if not examples_dir.exists():
        print("❌ examples/ directory not found")
        return 1

    print("=" * 70)
    print("Checking Examples for New DX Patterns")
    print("=" * 70)
    print()

    test_dirs = [
        "01_getting_started",
        "02_production_features",
        "03_streaming",
        "04_mcp_integration",
        "05_schema_and_types",
        "06_plugins",
        "advanced",
        "servers",
    ]

    all_clean = True
    total_files = 0
    total_issues = 0

    for dir_name in test_dirs:
        dir_path = examples_dir / dir_name

        if not dir_path.exists():
            continue

        examples = sorted(dir_path.glob("*.py"))

        if not examples:
            continue

        has_section_issues = False

        for example in examples:
            total_files += 1

            issues = check_dx_patterns(example)

            if issues:
                if not has_section_issues:
                    print(f"\n{dir_name}/")
                    print("-" * 70)
                    has_section_issues = True

                print(f"\n{example.name}:")
                for issue in issues:
                    print(f"  {issue}")
                    total_issues += 1

                all_clean = False

    print(f"\n{'=' * 70}")
    print(f"Checked {total_files} files")

    if all_clean:
        print("✓ All examples use new DX patterns!")
        return 0
    else:
        print(f"⚠️  Found {total_issues} DX pattern issues")
        print("\nRecommendations:")
        print("  1. Use 'from chuk_tool_processor import ...' for all imports")
        print("  2. Use 'async with ToolProcessor() as p:' for automatic cleanup")
        print("  3. Use 'IsolatedStrategy' instead of 'SubprocessStrategy'")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
