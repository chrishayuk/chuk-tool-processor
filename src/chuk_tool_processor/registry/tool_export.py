# chuk_tool_processor/registry/tool_export.py
"""
Helpers that expose all registered tools in various formats and
translate an OpenAI `function.name` back to the matching tool.
"""
from __future__ import annotations

from typing import Dict, List

from .provider import ToolRegistryProvider

# --------------------------------------------------------------------------- #
# internal cache so tool-name lookup is O(1)
# --------------------------------------------------------------------------- #
_OPENAI_NAME_CACHE: dict[str, object] | None = None


def _build_openai_name_cache() -> None:
    """Populate the global reverse-lookup table once."""
    global _OPENAI_NAME_CACHE
    if _OPENAI_NAME_CACHE is not None:  # already built
        return

    _OPENAI_NAME_CACHE = {}
    reg = ToolRegistryProvider.get_registry()

    for ns, key in reg.list_tools():
        tool = reg.get_tool(key, ns)

        # ▸ registry key  -> tool
        _OPENAI_NAME_CACHE[key] = tool

        # ▸ class name    -> tool  (legacy)
        _OPENAI_NAME_CACHE[tool.__class__.__name__] = tool

        # ▸ OpenAI name   -> tool  (may differ from both above)
        _OPENAI_NAME_CACHE[tool.to_openai()["function"]["name"]] = tool


# --------------------------------------------------------------------------- #
# public helpers
# --------------------------------------------------------------------------- #
def openai_functions() -> List[Dict]:
    """
    Return **all** registered tools in the exact schema the Chat-Completions
    API expects in its ``tools=[ … ]`` parameter.

    The ``function.name`` is always the *registry key* so that the round-trip
    (export → model → parser) stays consistent even when the class name and
    the registered key differ.
    """
    reg = ToolRegistryProvider.get_registry()
    specs: list[dict] = []

    for ns, key in reg.list_tools():
        tool = reg.get_tool(key, ns)
        spec = tool.to_openai()
        spec["function"]["name"] = key  # ensure round-trip consistency
        specs.append(spec)

    # Ensure the cache is built the first time we export
    _build_openai_name_cache()
    return specs


def tool_by_openai_name(name: str):
    """
    Map an OpenAI ``function.name`` back to the registered tool.

    Raises ``KeyError`` if the name is unknown.
    """
    _build_openai_name_cache()
    try:
        return _OPENAI_NAME_CACHE[name]  # type: ignore[index]
    except (KeyError, TypeError):
        raise KeyError(f"No tool registered for OpenAI name {name!r}") from None
