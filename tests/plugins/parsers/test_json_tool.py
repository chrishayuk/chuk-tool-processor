# tests/tool_processor/plugins/parsers/test_json_tool.py
"""
Tests for the async-native JsonToolPlugin that extracts ToolCall objects
from generic JSON payloads containing a ``tool_calls`` array.
"""

from __future__ import annotations

import json

import pytest

from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.plugins.parsers.json_tool import JsonToolPlugin


@pytest.fixture
def plugin() -> JsonToolPlugin:
    """Return a fresh plugin instance for each test."""
    return JsonToolPlugin()


# --------------------------------------------------------------------------- #
# Happy-path cases
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_try_parse_valid_json_single_call(plugin: JsonToolPlugin) -> None:
    raw = json.dumps({"tool_calls": [{"tool": "search", "arguments": {"q": "test"}}]})
    calls = await plugin.try_parse(raw)

    assert len(calls) == 1
    call = calls[0]
    assert isinstance(call, ToolCall)
    assert call.tool == "search"
    assert call.arguments == {"q": "test"}


@pytest.mark.asyncio
async def test_try_parse_valid_json_multiple_calls(plugin: JsonToolPlugin) -> None:
    raw = json.dumps(
        {
            "tool_calls": [
                {"tool": "a", "arguments": {"x": 1}},
                {"tool": "b", "arguments": {"y": 2}},
            ]
        }
    )
    calls = await plugin.try_parse(raw)
    assert [c.tool for c in calls] == ["a", "b"]


# --------------------------------------------------------------------------- #
# Negative / edge cases
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_try_parse_json_without_tool_calls(plugin: JsonToolPlugin) -> None:
    calls = await plugin.try_parse(json.dumps({"something_else": 123}))
    assert calls == []


@pytest.mark.asyncio
async def test_try_parse_malformed_json(plugin: JsonToolPlugin) -> None:
    calls = await plugin.try_parse("{invalid json")
    assert calls == []


@pytest.mark.asyncio
async def test_try_parse_invalid_call_structure(plugin: JsonToolPlugin) -> None:
    # Missing "tool" key inside an element
    raw = json.dumps({"tool_calls": [{"arguments": {}}]})
    calls = await plugin.try_parse(raw)
    assert calls == []


@pytest.mark.asyncio
async def test_try_parse_non_dict_json(plugin: JsonToolPlugin) -> None:
    # Top-level JSON is a list, not a dict
    calls = await plugin.try_parse(json.dumps([1, 2, 3]))
    assert calls == []
