# examples/plugins_custom_parser_demo.py
#!/usr/bin/env python
"""
Tiny demo that shows how easy it is to add **your own** parser plugin,
register it, and use it alongside the built-in ones.

Run with:  uv run examples/plugins_custom_parser_demo.py
"""

from __future__ import annotations

import asyncio
import json
import re

from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.plugins.discovery import plugin, plugin_registry

logger = get_logger(__name__)

# --------------------------------------------------------------------------- #
# ❶  A **custom parser** that recognises commands like
#       “!!weather location=Berlin units=metric”
# --------------------------------------------------------------------------- #


@plugin("parser")  # auto-register in the global registry
class AngleParser:
    """
    Recognise a double-exclamation command at the beginning of a sentence:

        !!weather location=Berlin units=metric
    """

    _COMMAND = re.compile(r"!!(?P<name>\w+)\s+(?P<args>.+)")

    async def try_parse(self, raw: str | object) -> list[ToolCall]:
        if not isinstance(raw, str):
            return []

        m = self._COMMAND.search(raw)
        if not m:
            return []

        name = m.group("name")
        arg_pairs = [p.split("=", 1) for p in m.group("args").split() if "=" in p]
        args = dict(arg_pairs)

        try:
            call = ToolCall(tool=name, arguments=args)
            return [call]
        except Exception as exc:  # pragma: no cover
            logger.debug("Cannot build ToolCall: %s", exc)
            return []


# --------------------------------------------------------------------------- #
# ❷  Simple playground
# --------------------------------------------------------------------------- #


async def main():
    # Make sure our plugin is discoverable - normally done at app start-up
    plugin_registry.register_plugin("parser", "AngleParser", AngleParser())

    raw = "Tell me the weather: !!weather location=Berlin units=metric"
    print("Input  :", raw)

    # Fetch the plugin from the registry
    parser: AngleParser | None = plugin_registry.get_plugin("parser", "AngleParser")  # type: ignore[assignment]

    if not parser:
        print("❌  AngleParser not found in registry")
        return

    calls = await parser.try_parse(raw)
    for c in calls:
        # Pydantic v2 helpers
        json_str = json.dumps(c.model_dump(mode="json"), indent=2)
        print("Parsed :", json_str)


if __name__ == "__main__":
    asyncio.run(main())
