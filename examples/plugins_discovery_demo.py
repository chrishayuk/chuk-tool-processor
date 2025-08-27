# examples/plugin_discovery_demo
#!/usr/bin/env python
"""
Demonstrate plugin discovery in *chuk_tool_processor*.

The script

1.  Loads all default plugins that ship with the library.
2.  Defines a tiny, custom parser plugin inside this very file.
3.  Runs discovery on *this* module so the custom parser is picked up.
4.  Shows the registry contents and exercises the custom parser.
"""

from __future__ import annotations

import asyncio
import sys

from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.plugins.discovery import (
    PluginDiscovery,
    discover_default_plugins,  # helper to load the library's own plugins
    plugin_registry,  # the global registry singleton
)
from chuk_tool_processor.plugins.parsers.base import ParserPlugin

# --------------------------------------------------------------------------- #
# 1.  Load the built-in plugins shipped with chuk_tool_processor
# --------------------------------------------------------------------------- #
discover_default_plugins()  # fills *plugin_registry* with default plugins


# --------------------------------------------------------------------------- #
# 2.  Define a *custom* parser plugin in-line (just for the demo)
# --------------------------------------------------------------------------- #
class AngleParser(ParserPlugin):
    """
    A silly example parser that recognises the literal words
    ``<angle> … </angle>`` in a string and turns them into a ToolCall.
    """

    async def try_parse(self, raw: str | object) -> list[ToolCall]:
        if isinstance(raw, str) and "<angle>" in raw and "</angle>" in raw:
            return [ToolCall(tool="angle", arguments={})]
        return []


# --------------------------------------------------------------------------- #
# 3.  Register the custom plugin via discovery on *this* module
# --------------------------------------------------------------------------- #
_this_module = sys.modules[__name__]
# trick PluginDiscovery into thinking this script is a package to scan
# (the module has to live in sys.modules for the walk to work)
if not hasattr(_this_module, "__path__"):
    _this_module.__path__ = []  # type: ignore[attr-defined]

PluginDiscovery(plugin_registry).discover_plugins([__name__])


# --------------------------------------------------------------------------- #
# Helper - show registry state
# --------------------------------------------------------------------------- #
def dump_registry() -> None:
    print("Registered plugins:")
    for category, names in plugin_registry.list_plugins().items():
        print(f"  {category}: {', '.join(sorted(names))}")


# --------------------------------------------------------------------------- #
# 4.  Tiny async demo using the custom parser
# --------------------------------------------------------------------------- #
async def main() -> None:
    dump_registry()

    # Grab the AngleParser from the registry and parse something
    angle_parser: AngleParser = plugin_registry.get_plugin("parser", "AngleParser")  # type: ignore[assignment]
    calls = await angle_parser.try_parse("please use <angle> brackets </angle> here")

    print("\nAngleParser produced:")
    for c in calls:
        print(" ", c)


if __name__ == "__main__":
    asyncio.run(main())
