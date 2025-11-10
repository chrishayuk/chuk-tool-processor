#!/usr/bin/env python3
"""Test all examples to ensure they work after consolidation."""

import subprocess
import sys
import time
from pathlib import Path

# Examples that need special handling
SKIP_EXAMPLES = {
    # OAuth examples need tokens
    "notion_oauth.py": "Requires OAuth token",
    "atlassian_sse.py": "Requires OAuth token",
    "oauth_error_handling.py": "Requires OAuth setup",
    # Interactive examples
    "wrappers_demo.py": "May have user prompts",
    # Server files (not runnable as tests)
    "mcp_sse_server.py": "Server file",
    "mcp_streamable_http_server.py": "Server file",
    "mcp_http_server.py": "Server file",
    "reliable_test_sse_server.py": "Server file",
    # Gateway examples need infrastructure
    "gateway_integration_demo.py": "Requires gateway infrastructure",
    "gateway_health_diagnostic.py": "Requires gateway infrastructure",
    # Context7 integration
    "context7_chuk_integration_demo.py": "Requires Context7 setup",
    "context7_integration.py": "Requires Context7 setup",
    # Transport error handling may need servers
    "transport_error_handling.py": "May require running servers",
    # Demo examples requiring external services
    "demo_bearer_token.py": "Requires running SSE server with bearer auth",
    "demo_langchain_tool.py": "Requires LangChain dependency",
    # Resilience demos requiring test servers
    "resilience_sse_demo.py": "Requires running SSE test server",
    "resilience_stdio_demo.py": "Requires running STDIO test server",
    # FastAPI example is a long-running server
    "fastapi_registry_example.py": "Long-running FastAPI server",
}

# Examples with longer timeouts
SLOW_EXAMPLES = {
    "streaming_demo.py": 30,
    "streaming_tool_calls_demo.py": 30,
    "observability_demo.py": 60,  # Needs extra time for retries and metrics
    "resilience_http_streamable_demo.py": 60,
    "resilience_substrategy_demo.py": 60,
}


def test_example(example_path: Path, timeout: int = 15) -> tuple[bool, str]:
    """Test a single example."""
    try:
        result = subprocess.run(
            ["uv", "run", "python", str(example_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=example_path.parent.parent.parent,  # Root of project
        )

        if result.returncode == 0:
            return True, "Success"
        else:
            error = result.stderr.strip() if result.stderr else result.stdout.strip()
            # Truncate long errors
            error = error[:200] + "..." if len(error) > 200 else error
            return False, f"Exit code {result.returncode}: {error}"

    except subprocess.TimeoutExpired:
        return False, f"Timeout after {timeout}s"
    except Exception as e:
        return False, f"Error: {str(e)}"


def main():
    examples_dir = Path("examples")

    if not examples_dir.exists():
        print("❌ examples/ directory not found")
        return 1

    print("=" * 70)
    print("Testing All Examples")
    print("=" * 70)
    print()

    # Organize examples by directory
    test_dirs = [
        ("01_getting_started", "Getting Started"),
        ("02_production_features", "Production Features"),
        ("03_streaming", "Streaming"),
        ("04_mcp_integration", "MCP Integration"),
        ("05_schema_and_types", "Schema & Types"),
        ("06_plugins", "Plugins"),
        ("advanced", "Advanced"),
        ("servers", "Servers"),
    ]

    total = 0
    passed = 0
    failed = 0
    skipped = 0

    results = []

    for dir_name, dir_label in test_dirs:
        dir_path = examples_dir / dir_name

        if not dir_path.exists():
            continue

        examples = sorted(dir_path.glob("*.py"))

        if not examples:
            continue

        print(f"\n{'=' * 70}")
        print(f"{dir_label} ({dir_name}/)")
        print(f"{'=' * 70}\n")

        for example in examples:
            total += 1
            rel_path = example.relative_to(examples_dir)

            # Check if should skip
            if example.name in SKIP_EXAMPLES:
                reason = SKIP_EXAMPLES[example.name]
                print(f"⊘ {rel_path}: SKIPPED ({reason})")
                skipped += 1
                results.append((rel_path, "SKIP", reason))
                continue

            # Get timeout
            timeout = SLOW_EXAMPLES.get(example.name, 15)

            # Test it
            print(f"Testing {rel_path}...", end=" ", flush=True)
            start = time.time()
            success, message = test_example(example, timeout)
            duration = time.time() - start

            if success:
                print(f"✓ PASS ({duration:.1f}s)")
                passed += 1
                results.append((rel_path, "PASS", f"{duration:.1f}s"))
            else:
                print(f"✗ FAIL: {message}")
                failed += 1
                results.append((rel_path, "FAIL", message))

    # Summary
    print(f"\n{'=' * 70}")
    print("Summary")
    print(f"{'=' * 70}\n")

    print(f"Total:   {total}")
    print(f"Passed:  {passed} ✓")
    print(f"Failed:  {failed} ✗")
    print(f"Skipped: {skipped} ⊘")

    if failed > 0:
        print(f"\n{'=' * 70}")
        print("Failed Examples")
        print(f"{'=' * 70}\n")

        for path, status, message in results:
            if status == "FAIL":
                print(f"✗ {path}")
                print(f"  {message}")
                print()

    print(f"\n{'=' * 70}")
    if failed == 0:
        print("✓ All testable examples passed!")
        return 0
    else:
        print(f"✗ {failed} example(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
