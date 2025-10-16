#!/usr/bin/env python3
"""
Simple STDIO transport example using chuk-mcp-echo server.

This is a minimal example demonstrating STDIO transport basics.

Prerequisites:
    chuk-mcp-echo server (installed automatically via uvx)

Usage:
    cd /Users/chrishay/chris-source/chuk-ai/chuk-tool-processor
    uv run python examples/stdio_echo.py
"""

import asyncio
import json
import logging
import sys
import tempfile
from pathlib import Path

from chuk_tool_processor.mcp.setup_mcp_stdio import setup_mcp_stdio

# Set up logging
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


async def create_echo_config() -> str:
    """Create server configuration for echo server."""
    config = {
        "mcpServers": {
            "echo": {
                "command": "uvx",
                "args": ["chuk-mcp-echo", "stdio"],
                "transport": "stdio"
            }
        }
    }

    # Write to temporary config file
    temp_dir = Path(tempfile.mkdtemp())
    config_file = temp_dir / "server_config.json"

    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"\n📝 Server configuration:")
    print(f"    Command: uvx")
    print(f"    Args: {config['mcpServers']['echo']['args']}")

    return str(config_file)


async def test_echo_server():
    """Test echo server via STDIO."""
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║          Simple STDIO Echo Server Test                                ║
║                                                                       ║
║  Minimal example of STDIO transport with chuk-mcp-echo                ║
╚══════════════════════════════════════════════════════════════════════╝
""")

    try:
        # Create config
        print("\n[1/2] Creating configuration...")
        config_file = await create_echo_config()

        # Connect
        print("\n[2/2] Connecting to echo server...")
        processor, stream_manager = await setup_mcp_stdio(
            config_file=config_file,
            servers=["echo"],
            namespace="echo",
            initialization_timeout=60.0,
        )

        print("    ✅ Connection successful!")

        # Get tools
        tools = stream_manager.get_all_tools()
        print(f"\n    Retrieved {len(tools)} tools:")
        for tool in tools:
            name = tool.get('name', 'unknown')
            desc = tool.get('description', 'No description')[:60]
            print(f"      • {name}: {desc}")

        await stream_manager.close()

        print("\n" + "="*70)
        print("✅ SUCCESS! Simple STDIO transport working")
        print("="*70)

        # Cleanup
        import shutil
        shutil.rmtree(Path(config_file).parent, ignore_errors=True)

        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        logger.exception("Detailed error:")
        return 1


async def main():
    """Main entry point."""
    try:
        return await test_echo_server()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
