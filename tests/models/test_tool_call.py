# tests/tool_processor/models/test_tool_call.py
import pytest
from pydantic import ValidationError

from chuk_tool_processor.models.tool_call import ToolCall


def test_tool_call_defaults():
    # Only 'tool' provided, arguments should default to empty dict
    call = ToolCall(tool="test_tool")
    assert call.tool == "test_tool"
    assert isinstance(call.arguments, dict)
    assert call.arguments == {}


def test_tool_call_with_arguments():
    # Provide custom arguments
    args = {"param1": 123, "param2": "value"}
    call = ToolCall(tool="another_tool", arguments=args)
    assert call.tool == "another_tool"
    # Ensure arguments dict is preserved
    assert call.arguments == args
    # Mutating original dict should not affect the model's stored arguments
    args["param1"] = 999
    assert call.arguments["param1"] == 123


@pytest.mark.parametrize("invalid_tool", [None, 123, "", [], {}])
def test_invalid_tool_field(invalid_tool):
    # tool must be a non-empty string
    with pytest.raises(ValidationError):
        ToolCall(tool=invalid_tool)


@pytest.mark.parametrize("invalid_args", [None, "not a dict", 123, [1, 2, 3]])
def test_invalid_arguments_field(invalid_args):
    # arguments must be a dict
    with pytest.raises(ValidationError):
        ToolCall(tool="valid_tool", arguments=invalid_args)


def test_extra_fields_ignored():
    # Unexpected extra fields should raise or be ignored depending on config
    # By default, Pydantic BaseModel ignores extra fields
    call = ToolCall(tool="toolX", extra_field="ignore me")  # type: ignore
    assert call.tool == "toolX"
    # Ensure extra_field is not set on the model
    assert not hasattr(call, "extra_field")


@pytest.mark.asyncio
async def test_to_dict():
    """Test converting ToolCall to dictionary."""
    call = ToolCall(tool="test_tool", namespace="custom", arguments={"key": "value"})
    result = await call.to_dict()

    assert result["tool"] == "test_tool"
    assert result["namespace"] == "custom"
    assert result["arguments"] == {"key": "value"}
    assert "id" in result
    assert isinstance(result["id"], str)


@pytest.mark.asyncio
async def test_from_dict():
    """Test creating ToolCall from dictionary."""
    data = {"id": "test-id-123", "tool": "my_tool", "namespace": "my_namespace", "arguments": {"param": 42}}
    call = await ToolCall.from_dict(data)

    assert call.id == "test-id-123"
    assert call.tool == "my_tool"
    assert call.namespace == "my_namespace"
    assert call.arguments == {"param": 42}


def test_str_representation():
    """Test string representation of ToolCall."""
    call = ToolCall(tool="example_tool", arguments={"arg1": "value1", "arg2": 123})
    str_repr = str(call)

    assert "ToolCall" in str_repr
    assert "example_tool" in str_repr
    assert "arg1" in str_repr
    assert "arg2" in str_repr


def test_str_representation_no_args():
    """Test string representation with no arguments."""
    call = ToolCall(tool="simple_tool")
    str_repr = str(call)

    assert "ToolCall" in str_repr
    assert "simple_tool" in str_repr
