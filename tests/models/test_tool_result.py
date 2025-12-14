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


class TestToolResultErrorInfo:
    """Tests for structured error info handling in ToolResult."""

    def test_error_info_populates_error_string(self):
        """Test that error_info populates error string when error is None (line 109)."""
        from chuk_tool_processor.core.exceptions import ErrorCategory, ErrorCode, ErrorInfo

        error_info = ErrorInfo(
            code=ErrorCode.TOOL_RATE_LIMITED,
            category=ErrorCategory.RATE_LIMIT,
            message="Rate limited",
            retryable=True,
            retry_after_ms=5000,
        )

        res = ToolResult(tool="test", result=None, error_info=error_info)

        # error should be populated from error_info.message
        assert res.error == "Rate limited"
        assert res.error_info == error_info

    def test_retryable_property_with_error_info(self):
        """Test retryable property when error_info is present (lines 133-135)."""
        from chuk_tool_processor.core.exceptions import ErrorCategory, ErrorCode, ErrorInfo

        # Retryable error
        error_info = ErrorInfo(
            code=ErrorCode.TOOL_RATE_LIMITED,
            category=ErrorCategory.RATE_LIMIT,
            message="Rate limited",
            retryable=True,
        )
        res = ToolResult(tool="test", result=None, error_info=error_info)
        assert res.retryable is True

        # Non-retryable error
        error_info_not_retryable = ErrorInfo(
            code=ErrorCode.TOOL_VALIDATION_ERROR,
            category=ErrorCategory.VALIDATION,
            message="Validation failed",
            retryable=False,
        )
        res2 = ToolResult(tool="test", result=None, error_info=error_info_not_retryable)
        assert res2.retryable is False

    def test_retryable_property_no_error(self):
        """Test retryable property returns True when no error (line 134)."""
        res = ToolResult(tool="test", result="ok")
        assert res.retryable is True

    def test_retry_after_ms_property(self):
        """Test retry_after_ms property (lines 145-147)."""
        from chuk_tool_processor.core.exceptions import ErrorCategory, ErrorCode, ErrorInfo

        # With retry_after_ms
        error_info = ErrorInfo(
            code=ErrorCode.TOOL_RATE_LIMITED,
            category=ErrorCategory.RATE_LIMIT,
            message="Rate limited",
            retryable=True,
            retry_after_ms=10000,
        )
        res = ToolResult(tool="test", result=None, error_info=error_info)
        assert res.retry_after_ms == 10000

        # Without error_info
        res2 = ToolResult(tool="test", result="ok")
        assert res2.retry_after_ms is None

    def test_error_category_property(self):
        """Test error_category property (lines 157-159)."""
        from chuk_tool_processor.core.exceptions import ErrorCategory, ErrorCode, ErrorInfo

        error_info = ErrorInfo(
            code=ErrorCode.TOOL_CIRCUIT_OPEN,
            category=ErrorCategory.CIRCUIT_OPEN,
            message="Circuit open",
            retryable=True,
        )
        res = ToolResult(tool="test", result=None, error_info=error_info)
        assert res.error_category == ErrorCategory.CIRCUIT_OPEN

        # Without error_info
        res2 = ToolResult(tool="test", result="ok")
        assert res2.error_category is None

    def test_error_code_property(self):
        """Test error_code property (lines 169-171)."""
        from chuk_tool_processor.core.exceptions import ErrorCategory, ErrorCode, ErrorInfo

        error_info = ErrorInfo(
            code=ErrorCode.TOOL_TIMEOUT,
            category=ErrorCategory.TIMEOUT,
            message="Timeout",
            retryable=True,
        )
        res = ToolResult(tool="test", result=None, error_info=error_info)
        assert res.error_code == ErrorCode.TOOL_TIMEOUT

        # Without error_info
        res2 = ToolResult(tool="test", result="ok")
        assert res2.error_code is None

    @pytest.mark.asyncio
    async def test_to_dict_with_error_info(self):
        """Test to_dict includes error_info when present (line 195)."""
        from chuk_tool_processor.core.exceptions import ErrorCategory, ErrorCode, ErrorInfo

        error_info = ErrorInfo(
            code=ErrorCode.TOOL_RATE_LIMITED,
            category=ErrorCategory.RATE_LIMIT,
            message="Rate limited",
            retryable=True,
            retry_after_ms=5000,
        )
        res = ToolResult(tool="test", result=None, error_info=error_info)

        result_dict = await res.to_dict()

        assert "error_info" in result_dict
        assert result_dict["error_info"]["code"] == "TOOL_RATE_LIMITED"
        assert result_dict["error_info"]["category"] == "rate_limit"
        assert result_dict["error_info"]["retryable"] is True
        assert result_dict["error_info"]["retry_after_ms"] == 5000

    @pytest.mark.asyncio
    async def test_from_dict_with_error_info(self):
        """Test from_dict deserializes error_info dict (line 222)."""
        data = {
            "id": "result-123",
            "tool": "my_tool",
            "result": None,
            "error": "Rate limited",
            "error_info": {
                "code": "TOOL_RATE_LIMITED",
                "category": "rate_limit",
                "message": "Rate limited",
                "retryable": True,
                "retry_after_ms": 5000,
                "details": {},
            },
            "start_time": "2024-01-01T12:00:00",
            "end_time": "2024-01-01T12:00:05",
            "machine": "localhost",
            "pid": 5678,
            "cached": False,
            "attempts": 1,
        }

        res = await ToolResult.from_dict(data)

        assert res.error_info is not None
        assert res.error_info.retryable is True
        assert res.error_info.retry_after_ms == 5000

    def test_create_error_with_string(self):
        """Test create_error with string error (lines 267-268)."""
        res = ToolResult.create_error(
            tool="test_tool",
            error="Something went wrong",
            attempts=3,
        )

        assert res.tool == "test_tool"
        assert res.error == "Something went wrong"
        assert res.error_info is not None
        assert res.attempts == 3
        assert res.result is None

    def test_create_error_with_exception(self):
        """Test create_error with exception."""
        from chuk_tool_processor.core.exceptions import ToolRateLimitedError

        exc = ToolRateLimitedError("api_tool", retry_after=10.0)

        res = ToolResult.create_error(
            tool="api_tool",
            error=exc,
            call_id="call-123",
        )

        assert res.tool == "api_tool"
        assert res.error_info is not None
        assert res.call_id == "call-123"
        # Error string should be populated from exception
        assert "api_tool" in res.error

    def test_create_error_with_custom_timestamps(self):
        """Test create_error with custom start/end times."""
        from datetime import datetime

        start = datetime(2024, 1, 1, 12, 0, 0)
        end = datetime(2024, 1, 1, 12, 0, 10)

        res = ToolResult.create_error(
            tool="test",
            error="Failed",
            start_time=start,
            end_time=end,
            machine="custom-host",
            pid=9999,
        )

        assert res.start_time == start
        assert res.end_time == end
        assert res.machine == "custom-host"
        assert res.pid == 9999
        assert res.duration == 10.0
