# tests/tool_processor/plugins/test_xml_tool.py
import pytest
import json
from chuk_tool_processor.plugins.parsers.xml_tool import XmlToolPlugin
from chuk_tool_processor.models.tool_call import ToolCall

@ pytest.fixture

def plugin():
    return XmlToolPlugin()

def test_try_parse_single_tag_with_args(plugin):
    raw = '<tool name="translate" args="{\"text\": \"Hello\", \"target\": \"es\"}"/>'
    calls = plugin.try_parse(raw)
    assert len(calls) == 1
    call = calls[0]
    assert isinstance(call, ToolCall)
    assert call.tool == "translate"
    assert call.arguments == {"text": "Hello", "target": "es"}


def test_try_parse_multiple_tags(plugin):
    raw = (
        '<tool name="a" args="{\"x\":1}"/>'
        ' some text '
        '<tool name="b" args="{\"y\":2}"/>'
    )
    calls = plugin.try_parse(raw)
    assert [c.tool for c in calls] == ["a", "b"]
    assert calls[0].arguments == {"x": 1}
    assert calls[1].arguments == {"y": 2}


def test_try_parse_tag_without_args(plugin):
    raw = '<tool name="noop" args=""/>'
    calls = plugin.try_parse(raw)
    assert len(calls) == 1
    call = calls[0]
    assert call.tool == "noop"
    assert call.arguments == {}


def test_try_parse_malformed_args(plugin):
    raw = '<tool name="broken" args="{invalid json}"/>'
    calls = plugin.try_parse(raw)
    assert len(calls) == 1
    call = calls[0]
    assert call.tool == "broken"
    # Malformed JSON yields empty args dict
    assert call.arguments == {}


def test_try_parse_no_tags(plugin):
    raw = 'no tools here'
    calls = plugin.try_parse(raw)
    assert calls == []


def test_try_parse_invalid_structure(plugin):
    # Even if args attribute is valid JSON, missing name should not match regex
    raw = '<tool wrong_attr="x"="{}"/>'
    calls = plugin.try_parse(raw)
    assert calls == []
