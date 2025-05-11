# tests/tool_processor/plugins/test_function_call_tool.py
import json
import pytest

from chuk_tool_processor.plugins.parsers.function_call_tool_plugin import (
    FunctionCallPlugin,
)
from chuk_tool_processor.models.tool_call import ToolCall


@pytest.fixture
def plugin():
    return FunctionCallPlugin()


@pytest.mark.asyncio
async def test_parse_valid_string_arguments(plugin):
    payload = {
        "function_call": {
            "name": "toolX",
            "arguments": json.dumps({"a": 1, "b": 2}),
        }
    }
    calls = await plugin.try_parse(json.dumps(payload))
    assert len(calls) == 1
    call = calls[0]
    assert isinstance(call, ToolCall)
    assert call.tool == "toolX"
    assert call.arguments == {"a": 1, "b": 2}


@pytest.mark.asyncio
async def test_parse_valid_dict_arguments(plugin):
    payload = {
        "function_call": {
            "name": "toolY",
            "arguments": {"x": "hello"},
        }
    }
    calls = await plugin.try_parse(json.dumps(payload))
    assert len(calls) == 1
    assert calls[0].tool == "toolY"
    assert calls[0].arguments == {"x": "hello"}


@pytest.mark.asyncio
async def test_parse_missing_function_call_field(plugin):
    calls = await plugin.try_parse(json.dumps({"foo": "bar"}))
    assert calls == []


@pytest.mark.asyncio
async def test_parse_invalid_json(plugin):
    calls = await plugin.try_parse("{not valid json")
    assert calls == []


@pytest.mark.asyncio
async def test_parse_empty_name(plugin):
    payload = {"function_call": {"name": "", "arguments": {"a": 1}}}
    calls = await plugin.try_parse(json.dumps(payload))
    assert calls == []


@pytest.mark.asyncio
async def test_parse_malformed_arguments_string(plugin):
    payload = {"function_call": {"name": "toolZ", "arguments": "{bad}"}}
    calls = await plugin.try_parse(json.dumps(payload))
    assert len(calls) == 1
    assert calls[0].tool == "toolZ"
    assert calls[0].arguments == {}


@pytest.mark.asyncio
async def test_parse_non_dict_arguments(plugin):
    payload = {"function_call": {"name": "toolW", "arguments": 123}}
    calls = await plugin.try_parse(json.dumps(payload))
    assert len(calls) == 1
    assert calls[0].tool == "toolW"
    assert calls[0].arguments == {}


@pytest.mark.asyncio
async def test_parse_missing_arguments_field(plugin):
    payload = {"function_call": {"name": "toolNoArgs"}}
    calls = await plugin.try_parse(json.dumps(payload))
    assert len(calls) == 1
    assert calls[0].tool == "toolNoArgs"
    assert calls[0].arguments == {}
