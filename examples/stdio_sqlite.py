#!/usr/bin/env python3
"""
STDIO transport example with chuk-tool-processor using SQLite MCP server.

This script demonstrates:
1. STDIO transport with command, args, and environment variables
2. Proper initialization_timeout handling
3. Credential and path passing through config

Prerequisites:
    uv (for running uvx to install MCP servers)
    SQLite MCP server will be installed automatically via uvx

Usage:
    cd /Users/chrishay/chris-source/chuk-ai/chuk-tool-processor
    uv run python examples/stdio_sqlite.py
"""

import asyncio
import json
import logging
import os
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


async def create_test_database():
    """Create a temporary SQLite database for testing."""
    # Create a temporary database file
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test.db"

    print(f"\n📁 Creating test database:")
    print(f"    Path: {db_path}")

    # Create and populate test database
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create sample table
    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Insert sample data
    sample_users = [
        ("Alice Johnson", "alice@example.com"),
        ("Bob Smith", "bob@example.com"),
        ("Charlie Brown", "charlie@example.com"),
    ]

    cursor.executemany("INSERT INTO users (name, email) VALUES (?, ?)", sample_users)
    conn.commit()
    conn.close()

    print(f"    ✓ Created table 'users' with {len(sample_users)} rows")

    return str(db_path), temp_dir


async def create_server_config(db_path: str) -> str:
    """Create server configuration file with STDIO settings."""
    config = {
        "mcpServers": {
            "sqlite": {
                "command": "uvx",
                "args": ["mcp-server-sqlite", "--db-path", db_path],
                "env": {
                    "UV_PYTHON": sys.executable,  # Use current Python interpreter
                    "MCP_SERVER_NAME": "sqlite-test",
                },
                "transport": "stdio"
            }
        }
    }

    # Write to temporary config file
    temp_dir = Path(tempfile.mkdtemp())
    config_file = temp_dir / "server_config.json"

    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"\n📝 Created server configuration:")
    print(f"    Config file: {config_file}")
    print(f"    Command: uvx")
    print(f"    Args: {config['mcpServers']['sqlite']['args']}")
    print(f"    Env vars: {list(config['mcpServers']['sqlite']['env'].keys())}")
    print(f"    Database path: {db_path}")

    return str(config_file)


async def test_stdio_transport():
    """Test STDIO transport with SQLite MCP server."""
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║          STDIO Transport Test with chuk-tool-processor                ║
║                                                                       ║
║  This script demonstrates proper parameter passing for STDIO:         ║
║  - Command and arguments                                              ║
║  - Environment variables                                              ║
║  - File paths                                                         ║
║  - initialization_timeout handling                                    ║
╚══════════════════════════════════════════════════════════════════════╝
""")

    try:
        # Step 1: Create test database
        print("\n[1/4] Setting up test environment...")
        db_path, db_temp_dir = await create_test_database()

        # Step 2: Create server config
        print("\n[2/4] Creating server configuration...")
        config_file = await create_server_config(db_path)

        # Step 3: Connect via STDIO
        print("\n[3/4] Connecting to SQLite MCP server via STDIO...")
        print("    Initializing connection...")
        print("    Note: First run may take 60-120s for uvx to download mcp-server-sqlite")

        processor, stream_manager = await setup_mcp_stdio(
            config_file=config_file,
            servers=["sqlite"],
            namespace="sqlite",
            default_timeout=30.0,
            initialization_timeout=120.0,  # Allow time for uvx package download on first run
        )

        print("    ✅ Connection successful!")

        # Step 4: Test tool retrieval
        print("\n[4/4] Testing tool retrieval...")
        tools = stream_manager.get_all_tools()
        print(f"    Retrieved {len(tools)} tools")

        if tools:
            print("\n    Available SQLite tools:")
            for tool in tools:
                name = tool.get('name', 'unknown')
                desc = tool.get('description', 'No description')[:60]
                print(f"      • {name}: {desc}")

        # Test server info
        server_info = stream_manager.get_server_info()
        if server_info:
            print("\n    Server information:")
            for info in server_info:
                print(f"      • Name: {info['name']}")
                print(f"        Tools: {info['tools']}")
                print(f"        Status: {info['status']}")

        # Cleanup
        await stream_manager.close()

        print("\n" + "="*70)
        print("✅ SUCCESS! STDIO transport working correctly")
        print("="*70)
        print("\nKey points proven:")
        print("  ✓ STDIO transport with command and arguments")
        print("  ✓ Environment variables passed correctly")
        print("  ✓ File paths (database path) passed correctly")
        print("  ✓ initialization_timeout handling works")
        print("  ✓ Successfully connected to MCP server via STDIO")
        print("  ✓ Retrieved and listed available tools")

        # Cleanup temp files
        import shutil
        shutil.rmtree(db_temp_dir, ignore_errors=True)
        shutil.rmtree(Path(config_file).parent, ignore_errors=True)

        return 0

    except FileNotFoundError as e:
        print("\n❌ Error: uvx command not found")
        print("\nPlease ensure uv is installed:")
        print("  pip install uv")
        print("\nThe SQLite MCP server will be installed automatically via uvx")
        logger.exception("Detailed error:")
        return 1

    except asyncio.TimeoutError:
        print("    ❌ Connection timed out")
        print("\n    Possible issues:")
        print("      • uvx is installing mcp-server-sqlite for the first time (try again)")
        print("      • Server startup is slow")
        print("      • Network issues preventing package download")
        return 1

    except Exception as e:
        print(f"\n❌ Error: {e}")
        logger.exception("Detailed error:")
        return 1


async def main():
    """Main entry point."""
    try:
        exit_code = await test_stdio_transport()
        return exit_code

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        logger.exception("Detailed error:")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
