#!/usr/bin/env python
"""
run_sse_demo.py
───────────────
Convenience script to run the complete SSE demo:
1. Starts the mock SSE server
2. Waits for it to be ready
3. Runs the client demo
4. Cleans up

Usage: python run_sse_demo.py
"""

import asyncio
import subprocess
import sys
import time
from pathlib import Path

import requests


def check_server_ready(url: str, max_attempts: int = 10) -> bool:
    """Check if the server is ready to accept connections."""
    for attempt in range(max_attempts):
        try:
            response = requests.get(f"{url}/health", timeout=2)
            if response.status_code == 200:
                return True
        except requests.RequestException:
            pass

        print(f"⏳ Waiting for server... (attempt {attempt + 1}/{max_attempts})")
        time.sleep(1)

    return False


async def run_demo():
    """Run the complete SSE demo."""
    server_url = "http://localhost:8000"

    # Get the correct project root (parent of the script location)
    script_path = Path(__file__).resolve()
    if script_path.parent.name == "examples":
        # If script is in examples/ directory
        project_root = script_path.parent.parent
    else:
        # If script is in project root
        project_root = script_path.parent

    print(f"📁 Project root: {project_root}")

    # Start the mock server
    print("🚀 Starting mock SSE server...")
    server_script = project_root / "examples" / "mcp_sse_server.py"
    client_script = project_root / "examples" / "mcp_sse_example_calling_usage.py"

    print(f"🖥️  Server script: {server_script}")
    print(f"🎯 Client script: {client_script}")

    if not server_script.exists():
        print(f"❌ Server script not found: {server_script}")
        print("Please save the test_sse_server.py to the examples/ directory")
        return

    if not client_script.exists():
        print(f"❌ Client script not found: {client_script}")
        return

    server_process = subprocess.Popen([sys.executable, str(server_script)])

    try:
        # Wait for server to be ready
        if not check_server_ready(server_url):
            print("❌ Server failed to start within timeout")
            return

        print("✅ Server is ready!")
        print("🔄 Running client demo...")

        # Run the client demo
        client_process = subprocess.run([sys.executable, str(client_script)])

        if client_process.returncode == 0:
            print("✅ Demo completed successfully!")
        else:
            print(f"❌ Demo failed with exit code: {client_process.returncode}")

    except KeyboardInterrupt:
        print("\n🛑 Demo interrupted by user")

    except Exception as e:
        print(f"❌ Demo error: {e}")

    finally:
        # Clean up server
        print("🧹 Cleaning up server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
        print("👋 Demo complete!")


if __name__ == "__main__":
    print("🎭 SSE Demo Runner")
    print("=" * 40)

    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        print("\n👋 Bye!")
    except Exception as e:
        print(f"❌ Runner error: {e}")
        sys.exit(1)
