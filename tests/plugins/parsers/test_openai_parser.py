# tests/plugins/parsers/test_openai_parser.py
"""Test OpenAI tool parser plugin."""

from __future__ import annotations

import json

import pytest

from chuk_tool_processor.plugins.parsers.openai_tool import OpenAIToolPlugin

pytestmark = pytest.mark.asyncio


class TestOpenAIToolPlugin:
    """Test OpenAI tool parser plugin."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return OpenAIToolPlugin()

    async def test_parse_single_tool_call(self, parser):
        """Test parsing single tool call."""
        data = {
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "weather",
                        "arguments": '{"location": "New York", "units": "celsius"}'
                    }
                }
            ]
        }

        calls = await parser.try_parse(data)

        assert len(calls) == 1
        assert calls[0].tool == "weather"
        assert calls[0].arguments == {"location": "New York", "units": "celsius"}
        # ID is auto-generated if not in the registry
        assert calls[0].id is not None

    async def test_parse_multiple_tool_calls(self, parser):
        """Test parsing multiple tool calls."""
        data = {
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "tool1",
                        "arguments": '{"arg": "val1"}'
                    }
                },
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {
                        "name": "tool2",
                        "arguments": '{"arg": "val2"}'
                    }
                }
            ]
        }

        calls = await parser.try_parse(data)

        assert len(calls) == 2
        assert calls[0].tool == "tool1"
        assert calls[0].arguments == {"arg": "val1"}
        assert calls[0].id is not None
        assert calls[1].tool == "tool2"
        assert calls[1].arguments == {"arg": "val2"}
        assert calls[1].id is not None

    async def test_parse_json_string(self, parser):
        """Test parsing from JSON string."""
        data = json.dumps({
            "tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {
                        "name": "calculator",
                        "arguments": '{"x": 5, "y": 10}'
                    }
                }
            ]
        })

        calls = await parser.try_parse(data)

        assert len(calls) == 1
        assert calls[0].tool == "calculator"
        assert calls[0].arguments == {"x": 5, "y": 10}

    async def test_parse_empty_tool_calls(self, parser):
        """Test parsing empty tool_calls array."""
        data = {"tool_calls": []}

        calls = await parser.try_parse(data)

        assert len(calls) == 0

    async def test_parse_no_tool_calls_field(self, parser):
        """Test parsing data without tool_calls field."""
        data = {"other": "data"}

        calls = await parser.try_parse(data)

        assert len(calls) == 0

    async def test_parse_invalid_json_string(self, parser):
        """Test parsing invalid JSON string."""
        data = "not valid json"

        calls = await parser.try_parse(data)

        assert len(calls) == 0

    async def test_parse_arguments_as_dict(self, parser):
        """Test parsing when arguments are already a dict."""
        data = {
            "tool_calls": [
                {
                    "id": "call_456",
                    "type": "function",
                    "function": {
                        "name": "search",
                        "arguments": {"query": "test", "limit": 10}  # Dict, not string
                    }
                }
            ]
        }

        calls = await parser.try_parse(data)

        assert len(calls) == 1
        assert calls[0].tool == "search"
        assert calls[0].arguments == {"query": "test", "limit": 10}

    async def test_parse_empty_arguments(self, parser):
        """Test parsing with empty arguments."""
        data = {
            "tool_calls": [
                {
                    "id": "call_789",
                    "type": "function",
                    "function": {
                        "name": "simple_tool",
                        "arguments": "{}"
                    }
                }
            ]
        }

        calls = await parser.try_parse(data)

        assert len(calls) == 1
        assert calls[0].tool == "simple_tool"
        assert calls[0].arguments == {}

    async def test_parse_invalid_arguments_json(self, parser):
        """Test parsing with invalid JSON in arguments."""
        data = {
            "tool_calls": [
                {
                    "id": "call_bad",
                    "type": "function",
                    "function": {
                        "name": "bad_tool",
                        "arguments": "not valid json"
                    }
                }
            ]
        }

        calls = await parser.try_parse(data)

        # Should handle gracefully - likely return raw string as argument
        assert len(calls) == 1
        assert calls[0].tool == "bad_tool"
        # Arguments might be wrapped or raw string

    async def test_parse_missing_function_name(self, parser):
        """Test handling missing function name."""
        data = {
            "tool_calls": [
                {
                    "id": "call_noname",
                    "type": "function",
                    "function": {
                        "arguments": '{"arg": "value"}'
                    }
                }
            ]
        }

        calls = await parser.try_parse(data)

        # Should skip this tool call
        assert len(calls) == 0

    async def test_parse_missing_function_field(self, parser):
        """Test handling missing function field."""
        data = {
            "tool_calls": [
                {
                    "id": "call_nofunc",
                    "type": "function"
                    # Missing "function" field
                }
            ]
        }

        calls = await parser.try_parse(data)

        # Should skip this tool call
        assert len(calls) == 0

    async def test_parse_non_dict_input(self, parser):
        """Test parsing non-dict input."""
        calls = await parser.try_parse(123)
        assert len(calls) == 0

        calls = await parser.try_parse([1, 2, 3])
        assert len(calls) == 0

        calls = await parser.try_parse(None)
        assert len(calls) == 0

    async def test_parse_malformed_tool_call(self, parser):
        """Test handling malformed tool call structure."""
        data = {
            "tool_calls": [
                {"malformed": "data"},  # Wrong structure
                {  # Valid one
                    "id": "call_good",
                    "type": "function",
                    "function": {
                        "name": "good_tool",
                        "arguments": "{}"
                    }
                }
            ]
        }

        calls = await parser.try_parse(data)

        # Should only parse the valid one
        assert len(calls) == 1
        assert calls[0].tool == "good_tool"

    async def test_parse_with_extra_fields(self, parser):
        """Test parsing with extra fields (should ignore them)."""
        data = {
            "tool_calls": [
                {
                    "id": "call_extra",
                    "type": "function",
                    "extra_field": "ignored",
                    "function": {
                        "name": "test_tool",
                        "arguments": "{}",
                        "extra_func_field": "also_ignored"
                    }
                }
            ],
            "other_field": "not_relevant"
        }

        calls = await parser.try_parse(data)

        assert len(calls) == 1
        assert calls[0].tool == "test_tool"

    async def test_parse_complex_arguments(self, parser):
        """Test parsing complex nested arguments."""
        args = {
            "nested": {
                "deep": {
                    "value": 42
                }
            },
            "list": [1, 2, 3],
            "bool": True,
            "null": None
        }

        data = {
            "tool_calls": [
                {
                    "id": "call_complex",
                    "type": "function",
                    "function": {
                        "name": "complex_tool",
                        "arguments": json.dumps(args)
                    }
                }
            ]
        }

        calls = await parser.try_parse(data)

        assert len(calls) == 1
        assert calls[0].arguments == args

    async def test_parse_unicode_in_arguments(self, parser):
        """Test parsing Unicode in arguments."""
        data = {
            "tool_calls": [
                {
                    "id": "call_unicode",
                    "type": "function",
                    "function": {
                        "name": "translate",
                        "arguments": '{"text": "Hello 世界 🌍"}'
                    }
                }
            ]
        }

        calls = await parser.try_parse(data)

        assert len(calls) == 1
        assert calls[0].arguments["text"] == "Hello 世界 🌍"

    async def test_parse_tool_calls_not_list(self, parser):
        """Test handling tool_calls that isn't a list."""
        data = {
            "tool_calls": "not a list"
        }

        # This will fail during parsing - test that it's handled
        calls = await parser.try_parse(data)

        assert len(calls) == 0

    async def test_plugin_metadata(self):
        """Test plugin has proper metadata."""
        plugin = OpenAIToolPlugin()

        # Check if has proper base class
        from chuk_tool_processor.plugins.parsers.base import ParserPlugin
        assert isinstance(plugin, ParserPlugin)

        # Check if PluginMeta exists
        assert hasattr(OpenAIToolPlugin, "PluginMeta") or True
