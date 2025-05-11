# tests/tool_processor/plugins/test_json_tool.py
import json
import pytest

from chuk_tool_processor.plugins.parsers.json_tool_plugin import JsonToolPlugin
from chuk_tool_processor.models.tool_call import ToolCall


@pytest.fixture
def plugin():
    return JsonToolPlugin()


@pytest.mark.asyncio
async def test_try_parse_valid_json_single_call(plugin):
    raw = json.dumps({"tool_calls": [{"tool": "search", "arguments": {"q": "test"}}]})
    calls = await plugin.try_parse(raw)
    assert len(calls) == 1
    call = calls[0]
    assert isinstance(call, ToolCall)
    assert call.tool == "search"
    assert call.arguments == {"q": "test"}


@pytest.mark.asyncio
async def test_try_parse_valid_json_multiple_calls(plugin):
    raw = json.dumps(
        {"tool_calls": [{"tool": "a", "arguments": {"x": 1}}, {"tool": "b", "arguments": {"y": 2}}]}
    )
    calls = await plugin.try_parse(raw)
    assert [c.tool for c in calls] == ["a", "b"]


@pytest.mark.asyncio
async def test_try_parse_json_without_tool_calls(plugin):
    calls = await plugin.try_parse(json.dumps({"something_else": 123}))
    assert calls == []


@pytest.mark.asyncio
async def test_try_parse_malformed_json(plugin):
    calls = await plugin.try_parse("{invalid json")
    assert calls == []


@pytest.mark.asyncio
async def test_try_parse_invalid_call_structure(plugin):
    raw = json.dumps({"tool_calls": [{"arguments": {}}]})  # missing 'tool'
    calls = await plugin.try_parse(raw)
    assert calls == []


@pytest.mark.asyncio
async def test_try_parse_non_dict_json(plugin):
    calls = await plugin.try_parse(json.dumps([1, 2, 3]))
    assert calls == []
