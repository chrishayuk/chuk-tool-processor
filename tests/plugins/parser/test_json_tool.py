# tests/tool_processor/plugins/test_json_tool.py
import pytest
import json
from chuk_tool_processor.plugins.parsers.json_tool_plugin import JsonToolPlugin
from chuk_tool_processor.models.tool_call import ToolCall

@pytest.fixture
def plugin():
    return JsonToolPlugin()

def test_try_parse_valid_json_single_call(plugin):
    raw = json.dumps({
        "tool_calls": [
            {"tool": "search", "arguments": {"q": "test"}}
        ]
    })
    calls = plugin.try_parse(raw)
    assert isinstance(calls, list)
    assert len(calls) == 1
    call = calls[0]
    assert isinstance(call, ToolCall)
    assert call.tool == "search"
    assert call.arguments == {"q": "test"}

def test_try_parse_valid_json_multiple_calls(plugin):
    raw = json.dumps({
        "tool_calls": [
            {"tool": "a", "arguments": {"x": 1}},
            {"tool": "b", "arguments": {"y": 2}}
        ]
    })
    calls = plugin.try_parse(raw)
    assert len(calls) == 2
    assert calls[0].tool == "a" and calls[1].tool == "b"

def test_try_parse_json_without_tool_calls(plugin):
    raw = json.dumps({"something_else": 123})
    calls = plugin.try_parse(raw)
    assert calls == []

def test_try_parse_malformed_json(plugin):
    raw = '{invalid json'
    calls = plugin.try_parse(raw)
    assert calls == []

def test_try_parse_invalid_call_structure(plugin):
    # tool_calls contains entries missing required fields
    raw = json.dumps({"tool_calls": [{"arguments": {}}]})
    calls = plugin.try_parse(raw)
    # ValidationError from missing 'tool' should be caught and result in empty list
    assert calls == []

def test_try_parse_non_dict_json(plugin):
    # JSON that is a list, not a dict
    raw = json.dumps([1, 2, 3])
    calls = plugin.try_parse(raw)
    assert calls == []
