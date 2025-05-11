# examples/demo_all_parser_plugins.py
"""
Demonstrates every async-native parser plugin shipped with
*chuk_tool_processor*.

What it does
------------
1.  Stubs a minimal `tool_by_openai_name` helper so the
    ``OpenAIToolPlugin`` can run without the full registry.
2.  Calls ``discover_default_plugins`` to load and register all built-in
    plugins.
3.  Sends four different raw messages—each crafted for one specific
    plugin—through *all* discovered parsers and prints the resulting
    ``ToolCall`` objects.

Run with:
    python demo_all_parser_plugins.py
"""
from __future__ import annotations

import asyncio
import json
import pprint
import sys
import types
from typing import Dict

from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.plugins.discovery import (
    discover_default_plugins,
    plugin_registry,
)

# --------------------------------------------------------------------------- #
# 0.  Provide a stub for `tool_by_openai_name` so OpenAIToolPlugin can work
# --------------------------------------------------------------------------- #
dummy_mod = types.ModuleType("chuk_tool_processor.registry.tool_export")


class DummyTool:  # simple placeholder class
    pass


def tool_by_openai_name(name: str):
    """Return a dummy tool class for any OpenAI function name."""
    return DummyTool


dummy_mod.tool_by_openai_name = tool_by_openai_name  # type: ignore[attr-defined]
sys.modules["chuk_tool_processor.registry.tool_export"] = dummy_mod

# --------------------------------------------------------------------------- #
# 1.  Discover / instantiate parser plugins
# --------------------------------------------------------------------------- #
discover_default_plugins()
parsers: Dict[str, object] = {
    name: plugin_registry.get_plugin("parser", name)
    for name in plugin_registry.list_plugins("parser")["parser"]
}

print("\nRegistered parser plugins:")
for p in parsers:
    print("  •", p)

# --------------------------------------------------------------------------- #
# 2.  Prepare test inputs – one per plugin
# --------------------------------------------------------------------------- #
RAW_MESSAGES = {
    # XmlToolPlugin ---------------------------------------------
    "xml_tag": (
        '<tool name="translate" '
        'args="{\\"text\\": \\"Hello\\", \\"target\\": \\"es\\"}"/>'
    ),
    # FunctionCallPlugin ----------------------------------------
    "function_call": json.dumps(
        {
            "function_call": {
                "name": "weather",
                "arguments": json.dumps({"location": "London"}),
            }
        }
    ),
    # JsonToolPlugin --------------------------------------------
    "json_tool_calls": json.dumps(
        {
            "tool_calls": [
                {"tool": "search", "arguments": {"q": "python asyncio"}},
            ]
        }
    ),
    # OpenAIToolPlugin ------------------------------------------
    "openai_tool_calls": json.dumps(
        {
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "dummy_tool",
                        "arguments": {"foo": "bar"},
                    },
                }
            ]
        }
    ),
}

# --------------------------------------------------------------------------- #
# 3.  Drive every raw message through every parser and show output
# --------------------------------------------------------------------------- #
async def run_demo() -> None:
    for label, raw in RAW_MESSAGES.items():
        print(f"\n=== Message: {label} ===")
        for parser_name, plugin in parsers.items():
            calls = await plugin.try_parse(raw)  # async call
            if calls:
                print(f"{parser_name}:")
                for c in calls:
                    pprint.pprint(c.model_dump(mode="json"))
            else:
                print(f"{parser_name}: (no match)")


if __name__ == "__main__":
    asyncio.run(run_demo())
