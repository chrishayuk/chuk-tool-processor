# tests/tool_processor/plugins/test_function_call_tool.py
import pytest
import json

from chuk_tool_processor.plugins.parsers.function_call_tool_plugin import FunctionCallPlugin
from chuk_tool_processor.models.tool_call import ToolCall

@pytest.fixture
def plugin():
    return FunctionCallPlugin()


def test_parse_valid_string_arguments(plugin):
    # Arguments provided as JSON-encoded string
    payload = {
        "function_call": {
            "name": "toolX",
            "arguments": json.dumps({"a": 1, "b": 2})
        }
    }
    raw = json.dumps(payload)
    calls = plugin.try_parse(raw)
    assert len(calls) == 1
    call = calls[0]
    assert isinstance(call, ToolCall)
    assert call.tool == "toolX"
    assert call.arguments == {"a": 1, "b": 2}


def test_parse_valid_dict_arguments(plugin):
    # Arguments provided as a dict
    payload = {
        "function_call": {
            "name": "toolY",
            "arguments": {"x": "hello"}
        }
    }
    raw = json.dumps(payload)
    calls = plugin.try_parse(raw)
    assert len(calls) == 1
    call = calls[0]
    assert call.tool == "toolY"
    assert call.arguments == {"x": "hello"}


def test_parse_missing_function_call_field(plugin):
    # No function_call in payload
    raw = json.dumps({"foo": "bar"})
    calls = plugin.try_parse(raw)
    assert calls == []


def test_parse_invalid_json(plugin):
    # Malformed JSON string
    raw = '{not valid json'
    calls = plugin.try_parse(raw)
    assert calls == []


def test_parse_empty_name(plugin):
    # Empty tool name should be ignored
    payload = {"function_call": {"name": "", "arguments": {"a": 1}}}
    calls = plugin.try_parse(json.dumps(payload))
    assert calls == []


def test_parse_malformed_arguments_string(plugin):
    # Arguments string is not valid JSON
    payload = {"function_call": {"name": "toolZ", "arguments": "{bad}"}}
    calls = plugin.try_parse(json.dumps(payload))
    assert len(calls) == 1
    call = calls[0]
    assert call.tool == "toolZ"
    assert call.arguments == {}


def test_parse_non_dict_arguments(plugin):
    # Arguments field is not a dict or JSON string
    payload = {"function_call": {"name": "toolW", "arguments": 123}}
    calls = plugin.try_parse(json.dumps(payload))
    assert len(calls) == 1
    call = calls[0]
    assert call.tool == "toolW"
    assert call.arguments == {}


def test_parse_missing_arguments_field(plugin):
    # function_call has no arguments key
    payload = {"function_call": {"name": "toolNoArgs"}}
    calls = plugin.try_parse(json.dumps(payload))
    assert len(calls) == 1
    call = calls[0]
    assert call.tool == "toolNoArgs"
    assert call.arguments == {}
