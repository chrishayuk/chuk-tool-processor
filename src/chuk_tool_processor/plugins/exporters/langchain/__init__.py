# chuk_tool_processor/plugins/exporters/langchain/__init__.py
"""
Exporter plugin: expose every registry tool as a LangChain `BaseTool`.
Category = "exporter", Name = "langchain"
"""
from __future__ import annotations

from chuk_tool_processor.plugins.discovery import plugin_registry
from .bridge import registry_as_langchain_tools   # lazy import happens inside

# --------------------------------------------------------------------------- #
# build the exporter instance *once* ---------------------------------------- #
# --------------------------------------------------------------------------- #
class _LCExporter:
    """Callable wrapper – behaves like any other exporter plugin."""

    def __call__(self, *, filter_names: list[str] | None = None):
        return registry_as_langchain_tools(filter_names)

    # keep the `.run()` synonym that LangChain likes to use
    run = __call__


# --------------------------------------------------------------------------- #
# register **the instance** (not the factory) ------------------------------- #
# --------------------------------------------------------------------------- #
plugin_registry.register_plugin(      # type: ignore[attr-defined]
    "exporter",
    "langchain",
    _LCExporter(),                    # ← note the *call* – we store the object
)
