#!/usr/bin/env python
# examples/plugins_builtins_demo.py
#!/usr/bin/env python
# examples/plugins_builtins_demo.py
"""
Demonstrate all *built-in* async parser plugins that ship with
``chuk_tool_processor``:

• FunctionCallPlugin   – single ``{"function_call": {...}}`` payload
• JsonToolPlugin       – generic ``{"tool_calls": [...]}`` arrays
• OpenAIToolPlugin     – OpenAI chat-completions style ``tool_calls`` objects
• XmlToolPlugin        – single-line ``<tool …/>`` tags

For each plugin we feed a representative input string and print the resulting
``ToolCall`` objects.
"""

from __future__ import annotations

import asyncio
import json
import textwrap
from typing import Dict, List

from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.plugins.discovery import discover_default_plugins, plugin_registry

# --------------------------------------------------------------------------- #
# 1.  Prepare demo payloads keyed by plugin name
# --------------------------------------------------------------------------- #

DEMO_PAYLOADS: Dict[str, str] = {
    # ──────────────────────────────────────────────────────────────────────
    # FunctionCallPlugin
    # ──────────────────────────────────────────────────────────────────────
    "FunctionCallPlugin": json.dumps(
        {
            "function_call": {
                "name": "greet",
                "arguments": json.dumps({"who": "world"}),
            }
        }
    ),
    # ──────────────────────────────────────────────────────────────────────
    # JsonToolPlugin
    # ──────────────────────────────────────────────────────────────────────
    "JsonToolPlugin": json.dumps(
        {
            "tool_calls": [
                {"tool": "search", "arguments": {"q": "asyncio"}},
                {"tool": "calc", "arguments": {"expr": "2+2"}},
            ]
        }
    ),
    # ──────────────────────────────────────────────────────────────────────
    # OpenAIToolPlugin
    # ──────────────────────────────────────────────────────────────────────
    "OpenAIToolPlugin": json.dumps(
        {
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "weather",
                        "arguments": json.dumps({"location": "Paris"}),
                    },
                }
            ]
        }
    ),
    # ──────────────────────────────────────────────────────────────────────
    # XmlToolPlugin
    # ──────────────────────────────────────────────────────────────────────
    "XmlToolPlugin": '<tool name="translate" args="{\\"text\\": \\"Hello\\", \\"target\\": \\"es\\"}"/>',
}

# --------------------------------------------------------------------------- #
# 2.  Async helper to run each parser
# --------------------------------------------------------------------------- #


async def run_demo() -> None:
    # Make sure the default plugins are in the registry
    discover_default_plugins()

    # Grab the *names* of registered parser plugins
    parser_names: List[str] = plugin_registry.list_plugins("parser")["parser"]
    print("Registered parser plugins:")
    for n in parser_names:
        print(f"  • {n}")

    print("-" * 60)

    # Iterate over them and try to parse the demo payload for each
    for name in parser_names:
        payload = DEMO_PAYLOADS.get(name, "")
        parser = plugin_registry.get_plugin("parser", name)

        if parser is None:
            continue  # should not happen

        # Run the parser
        calls: List[ToolCall] = await parser.try_parse(payload)

        # Pretty-print
        snippet = textwrap.shorten(payload, width=80, placeholder="…")
        print(f"\n[{name}]  input: {snippet}")
        if not calls:
            print("  → (no ToolCalls produced)")
        else:
            for tc in calls:
                print(f"  → ToolCall({tc.tool}, {tc.arguments})")


# --------------------------------------------------------------------------- #
# 3.  Entrypoint
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    asyncio.run(run_demo())
