#!/usr/bin/env python
"""
Example script demonstrating how to create and use custom plugins.

This example shows:
1. Creating custom parser plugins
2. Registering plugins with the plugin system
3. Auto-discovering built-in parsers
4. Using plugins with the tool processor
"""

import asyncio
import sys
import os
import re
import json
from typing import List, Dict, Any

# Make project importable when running script directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.plugins.discovery import plugin, plugin_registry, discover_plugins
from chuk_tool_processor.core.processor import ToolProcessor
from chuk_tool_processor.registry import register_tool, ToolRegistryProvider
from chuk_tool_processor.registry.providers.memory import InMemoryToolRegistry
from chuk_tool_processor.logging import get_logger

# Set up logger
logger = get_logger("plugin_example")

# --- Example 1: YAML parser plugin ---
@plugin(category="parser", name="yaml_tool")
class YamlToolParser:
    """
    Parse YAML-like code blocks:
    ```yaml
    tool: name
    args:
      key: value
    ```
    """
    def try_parse(self, raw: str) -> List[ToolCall]:
        calls: List[ToolCall] = []
        pattern = r"```yaml\s+(.*?)```"
        for match in re.finditer(pattern, raw, re.DOTALL):
            block = match.group(1).strip().splitlines()
            if not block or not block[0].startswith("tool:"):
                continue
            tool_name = block[0].split("tool:",1)[1].strip()
            args: Dict[str, Any] = {}
            indent = None
            for line in block[1:]:
                if line.strip().startswith("args:"):
                    indent = len(line) - len(line.lstrip())
                    continue
                if indent is None or not line.strip():
                    continue
                curr = len(line) - len(line.lstrip())
                if curr <= indent:
                    break
                key,val = [p.strip() for p in line.split(":",1)]
                if val.lower() in ("true","false"):
                    val = val.lower() == "true"
                elif val.isdigit():
                    val = int(val)
                elif val.replace('.', '',1).isdigit():
                    val = float(val)
                args[key] = val
            calls.append(ToolCall(tool=tool_name, arguments=args))
        return calls

# --- Example 2: Bracket parser plugin ---
@plugin(category="parser", name="bracket_tool")
class BracketToolParser:
    """
    Parse [tool:name key=val ...] calls in text.
    """
    def try_parse(self, raw: str) -> List[ToolCall]:
        calls: List[ToolCall] = []
        pattern = r"\[tool:([^\s\]]+)([^\]]*)\]"
        for match in re.finditer(pattern, raw):
            tool_name = match.group(1)
            args_str = match.group(2).strip()
            args: Dict[str, Any] = {}
            if args_str:
                arg_pat = r'([^\s=]+)=(?:([^\s"]+)|"([^"]*)")'
                for am in re.finditer(arg_pat, args_str):
                    k = am.group(1)
                    v = am.group(2) if am.group(2) is not None else am.group(3)
                    if isinstance(v, str) and v.lower() in ("true","false"):
                        v = v.lower() == "true"
                    elif isinstance(v, str) and v.isdigit():
                        v = int(v)
                    elif isinstance(v, str) and v.replace('.', '',1).isdigit():
                        v = float(v)
                    args[k] = v
            calls.append(ToolCall(tool=tool_name, arguments=args))
        return calls

# --- Simple greeting tool ---
@register_tool(name="greet")
class GreetingTool:
    """A simple tool for generating greetings."""
    def execute(self, name: str, language: str = "english") -> Dict[str, Any]:
        messages = {
            "english": f"Hello, {name}!",
            "spanish": f"¡Hola, {name}!",
            "french": f"Bonjour, {name}!",
        }
        return {"message": messages.get(language.lower(), messages["english"]),
                "language": language, "name": name}

# Helper to test parsing + execution
def _print_results(results: List[Any]):
    if not results:
        print("No calls found.")
        return
    for idx, res in enumerate(results,1):
        if res.error:
            print(f"{idx}. {res.tool} -> ERROR: {res.error}")
        else:
            out = json.dumps(res.result, indent=2) if isinstance(res.result, dict) else res.result
            print(f"{idx}. {res.tool} -> {out}")

async def main():
    print("\n=== Plugin Example Demo ===\n")

    # 1) Build & register greeting tool in registry
    registry = InMemoryToolRegistry()
    registry.register_tool(GreetingTool(), name="greet")
    ToolRegistryProvider.set_registry(registry)

    # 2) Auto-discover built-in parser plugins
    discover_plugins(["chuk_tool_processor.plugins.parsers"])

    # 3) Manually register custom parsers (decorated classes)
    for cls in (YamlToolParser, BracketToolParser):
        meta = getattr(cls, '_plugin_meta', {})
        plugin_registry.register_plugin(meta['category'], meta['name'], cls())

    # 4) Show all registered parsers
    print("Registered parser plugins:")
    for cat, names in plugin_registry.list_plugins().items():
        if cat == 'parser':
            for name in names:
                print(f" - {name}")

    # 5) Create processor
    processor = ToolProcessor()

    # Test inputs
    tests = [
        ("YAML", "```yaml\ntool: greet\nargs:\n  name: Alice\n  language: french\n```"),
        ("Bracket", "[tool:greet name=Bob language=spanish]"),
        ("JSON", "{\"function_call\":{\"name\":\"greet\",\"arguments\":{\"name\":\"Eve\",\"language\":\"english\"}}}")
    ]
    for title, text in tests:
        print(f"\n-- {title} Test --")
        results = await processor.process_text(text)
        _print_results(results)

if __name__ == "__main__":
    asyncio.run(main())
