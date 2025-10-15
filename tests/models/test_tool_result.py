# tests/tool_processor/models/test_tool_result.py
import pytest
from pydantic import ValidationError

from chuk_tool_processor.models.tool_result import ToolResult


def test_tool_result_defaults():
    # Provide only required fields
    res = ToolResult(tool="t1", result={"data": 42})
    assert res.tool == "t1"
    assert res.result == {"data": 42}
    assert res.error is None


def test_tool_result_with_error():
    # Provide explicit error
    res = ToolResult(tool="t2", result=None, error="failure")
    assert res.tool == "t2"
    assert res.result is None
    assert res.error == "failure"


@pytest.mark.parametrize("invalid_tool", [None, 123, "", [], {}])
def test_invalid_tool_field(invalid_tool):
    # tool must be non-empty string
    with pytest.raises(ValidationError):
        ToolResult(tool=invalid_tool, result=123)


@pytest.mark.parametrize("invalid_error", [123, [], {}, object()])
def test_invalid_error_field(invalid_error):
    # error must be Optional[str]
    with pytest.raises(ValidationError):
        ToolResult(tool="t", result="ok", error=invalid_error)


@pytest.mark.parametrize("invalid_result", [pytest.mark.skip, object()])
def test_invalid_result_field(invalid_result):
    # result can be any type, so no validation error
    # Using a dummy object should work
    dummy = invalid_result
    res = ToolResult(tool="t3", result=dummy)
    assert res.result is dummy


def test_extra_fields_ignored():
    # Unexpected extra fields should be ignored
    res = ToolResult(tool="t4", result=123, extra="ignore")  # type: ignore
    assert res.tool == "t4"
    assert not hasattr(res, "extra")


def test_is_success_property():
    """Test is_success property."""
    # Success case
    res_success = ToolResult(tool="test", result="ok", error=None)
    assert res_success.is_success is True

    # Error case
    res_error = ToolResult(tool="test", result=None, error="failed")
    assert res_error.is_success is False


def test_duration_property():
    """Test duration property calculates correctly."""
    from datetime import datetime

    start = datetime(2024, 1, 1, 12, 0, 0)
    end = datetime(2024, 1, 1, 12, 0, 5)  # 5 seconds later

    res = ToolResult(tool="test", result="ok", start_time=start, end_time=end)
    assert res.duration == 5.0


def test_duration_property_with_defaults():
    """Test duration property with default timestamps."""
    # When no times are provided, defaults are used
    res = ToolResult(tool="test", result="ok")
    # Duration should be very small (near 0) since both timestamps are generated at nearly the same time
    assert res.duration >= 0.0
    assert res.duration < 1.0  # Should complete in less than 1 second


@pytest.mark.asyncio
async def test_to_dict():
    """Test converting ToolResult to dictionary."""
    from datetime import datetime

    start = datetime(2024, 1, 1, 12, 0, 0)
    end = datetime(2024, 1, 1, 12, 0, 5)

    res = ToolResult(
        tool="test_tool",
        result={"key": "value"},
        error=None,
        start_time=start,
        end_time=end,
        machine="host1",
        pid=1234,
        cached=True,
        attempts=2,
        stream_id="stream-123",
        is_partial=False,
    )

    result_dict = await res.to_dict()

    assert result_dict["tool"] == "test_tool"
    assert result_dict["result"] == {"key": "value"}
    assert result_dict["error"] is None
    assert result_dict["success"] is True
    assert result_dict["duration"] == 5.0
    assert result_dict["machine"] == "host1"
    assert result_dict["pid"] == 1234
    assert result_dict["cached"] is True
    assert result_dict["attempts"] == 2
    assert result_dict["stream_id"] == "stream-123"
    assert result_dict["is_partial"] is False


def test_create_stream_chunk():
    """Test creating a partial streaming result."""
    chunk = ToolResult.create_stream_chunk(tool="streaming_tool", result={"chunk": 1})

    assert chunk.tool == "streaming_tool"
    assert chunk.result == {"chunk": 1}
    assert chunk.error is None
    assert chunk.is_partial is True
    assert chunk.stream_id is not None


def test_create_stream_chunk_with_id():
    """Test creating stream chunk with custom stream_id."""
    chunk = ToolResult.create_stream_chunk(tool="streaming_tool", result={"chunk": 1}, stream_id="custom-stream-id")

    assert chunk.stream_id == "custom-stream-id"
    assert chunk.is_partial is True


@pytest.mark.asyncio
async def test_from_dict():
    """Test creating ToolResult from dictionary."""
    data = {
        "id": "result-123",
        "tool": "my_tool",
        "result": {"output": "data"},
        "error": None,
        "start_time": "2024-01-01T12:00:00",
        "end_time": "2024-01-01T12:00:05",
        "machine": "localhost",
        "pid": 5678,
        "cached": False,
        "attempts": 1,
        "stream_id": None,
        "is_partial": False,
    }

    res = await ToolResult.from_dict(data)

    assert res.id == "result-123"
    assert res.tool == "my_tool"
    assert res.result == {"output": "data"}
    assert res.error is None
    assert res.machine == "localhost"
    assert res.pid == 5678


def test_str_representation_success():
    """Test string representation for successful result."""
    res = ToolResult(tool="example_tool", result="ok", error=None)
    str_repr = str(res)

    assert "ToolResult" in str_repr
    assert "example_tool" in str_repr
    assert "success" in str_repr
    assert "duration" in str_repr


def test_str_representation_error():
    """Test string representation for error result."""
    res = ToolResult(tool="example_tool", result=None, error="Something went wrong")
    str_repr = str(res)

    assert "ToolResult" in str_repr
    assert "example_tool" in str_repr
    assert "error" in str_repr
    assert "Something went wrong" in str_repr
