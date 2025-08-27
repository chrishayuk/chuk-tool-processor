# tests/logging/test_formatter.py
"""
Tests for the structured formatter.
"""

import json
import logging
from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from chuk_tool_processor.logging.formatter import StructuredFormatter


class SampleModel(BaseModel):
    """Sample model for testing serialization."""

    name: str
    value: int


def test_formatter_initialization():
    """Test StructuredFormatter initialization."""
    formatter = StructuredFormatter()
    assert isinstance(formatter, logging.Formatter)


def test_json_default_pydantic():
    """Test JSON serialization of Pydantic models."""
    formatter = StructuredFormatter()
    model = SampleModel(name="test", value=123)

    result = formatter._json_default(model)
    assert isinstance(result, dict)
    assert result == {"name": "test", "value": 123}


def test_json_default_datetime():
    """Test JSON serialization of datetime objects."""
    formatter = StructuredFormatter()
    dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)

    result = formatter._json_default(dt)
    assert isinstance(result, str)
    assert result == "2023-01-01T12:00:00+00:00"


def test_json_default_date():
    """Test JSON serialization of date objects."""
    formatter = StructuredFormatter()
    d = date(2023, 1, 1)

    result = formatter._json_default(d)
    assert isinstance(result, str)
    assert result == "2023-01-01"


def test_json_default_set():
    """Test JSON serialization of sets."""
    formatter = StructuredFormatter()
    sample_set = {1, 2, 3}

    result = formatter._json_default(sample_set)
    assert isinstance(result, list)
    assert sorted(result) == [1, 2, 3]


def test_json_default_frozenset():
    """Test JSON serialization of frozensets."""
    formatter = StructuredFormatter()
    sample_frozenset = frozenset([1, 2, 3])

    result = formatter._json_default(sample_frozenset)
    assert isinstance(result, list)
    assert sorted(result) == [1, 2, 3]


def test_json_default_fallback():
    """Test JSON serialization fallback for unsupported types."""
    formatter = StructuredFormatter()

    class CustomClass:
        def __str__(self):
            return "custom-str"

    obj = CustomClass()
    result = formatter._json_default(obj)
    assert result == "custom-str"


def test_format_basic():
    """Test basic formatting of a log record."""
    formatter = StructuredFormatter()

    # Create a record
    record = MagicMock()
    record.created = datetime.now(UTC).timestamp()
    record.levelname = "INFO"
    record.getMessage.return_value = "Test message"
    record.name = "test.logger"
    record.process = 1234
    record.thread = 5678
    record.filename = "test.py"
    record.lineno = 42
    record.funcName = "test_function"
    record.exc_info = None

    # Format the record
    result = formatter.format(record)

    # Should be valid JSON
    data = json.loads(result)

    # Check required fields
    assert "timestamp" in data
    assert data["level"] == "INFO"
    assert data["message"] == "Test message"
    assert data["logger"] == "test.logger"
    assert data["pid"] == 1234
    assert data["thread"] == 5678
    assert data["file"] == "test.py"
    assert data["line"] == 42
    assert data["function"] == "test_function"


def test_format_with_context():
    """Test formatting with context."""
    formatter = StructuredFormatter()

    # Create a record with context
    record = MagicMock()
    record.created = datetime.now(UTC).timestamp()
    record.levelname = "INFO"
    record.getMessage.return_value = "Test message"
    record.name = "test.logger"
    record.process = 1234
    record.thread = 5678
    record.filename = "test.py"
    record.lineno = 42
    record.funcName = "test_function"
    record.exc_info = None
    record.context = {"request_id": "test-123", "user_id": "user-456"}

    # Format the record
    result = formatter.format(record)

    # Parse JSON
    data = json.loads(result)

    # Check context
    assert "context" in data
    assert data["context"]["request_id"] == "test-123"
    assert data["context"]["user_id"] == "user-456"


def test_format_with_extra():
    """Test formatting with extra fields."""
    formatter = StructuredFormatter()

    # Create a record with extra
    record = MagicMock()
    record.created = datetime.now(UTC).timestamp()
    record.levelname = "INFO"
    record.getMessage.return_value = "Test message"
    record.name = "test.logger"
    record.process = 1234
    record.thread = 5678
    record.filename = "test.py"
    record.lineno = 42
    record.funcName = "test_function"
    record.exc_info = None
    record.extra = {"correlation_id": "corr-123", "service": "test-service"}

    # Format the record
    result = formatter.format(record)

    # Parse JSON
    data = json.loads(result)

    # Check extra fields
    assert data["correlation_id"] == "corr-123"
    assert data["service"] == "test-service"


def test_format_with_exception():
    """Test formatting with exception info."""
    formatter = StructuredFormatter()

    # Create a record with exception
    record = MagicMock()
    record.created = datetime.now(UTC).timestamp()
    record.levelname = "ERROR"
    record.getMessage.return_value = "Error message"
    record.name = "test.logger"
    record.process = 1234
    record.thread = 5678
    record.filename = "test.py"
    record.lineno = 42
    record.funcName = "test_function"
    record.exc_info = (ValueError, ValueError("Test error"), None)

    # Mock formatException
    formatter.formatException = MagicMock(return_value="Traceback info")

    # Format the record
    result = formatter.format(record)

    # Parse JSON
    data = json.loads(result)

    # Check exception info
    assert "traceback" in data
    assert data["traceback"] == "Traceback info"


def test_format_complex_object():
    """Test formatting with complex nested objects."""
    formatter = StructuredFormatter()

    # Create a complex object
    complex_obj = {
        "user": SampleModel(name="test", value=123),
        "dates": [
            datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC),
            datetime(2023, 1, 2, 12, 0, 0, tzinfo=UTC),
        ],
        "tags": {"tag1", "tag2", "tag3"},
    }

    # Create a record with complex object in context
    record = MagicMock()
    record.created = datetime.now(UTC).timestamp()
    record.levelname = "INFO"
    record.getMessage.return_value = "Test message"
    record.name = "test.logger"
    record.process = 1234
    record.thread = 5678
    record.filename = "test.py"
    record.lineno = 42
    record.funcName = "test_function"
    record.exc_info = None
    record.context = {"complex": complex_obj}

    # Format the record
    result = formatter.format(record)

    # Should not raise exceptions
    data = json.loads(result)

    # Check complex object serialization
    assert "context" in data
    assert "complex" in data["context"]
    assert "user" in data["context"]["complex"]
    assert data["context"]["complex"]["user"] == {"name": "test", "value": 123}
    assert "dates" in data["context"]["complex"]
    assert len(data["context"]["complex"]["dates"]) == 2
    assert "tags" in data["context"]["complex"]
    assert sorted(data["context"]["complex"]["tags"]) == ["tag1", "tag2", "tag3"]


def test_timestamp_format():
    """Test that timestamp is properly formatted."""
    formatter = StructuredFormatter()

    # Create a record with known timestamp
    record = MagicMock()
    # 2023-01-01T12:00:00Z
    record.created = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC).timestamp()
    record.levelname = "INFO"
    record.getMessage.return_value = "Test message"
    record.name = "test.logger"
    record.process = 1234
    record.thread = 5678
    record.filename = "test.py"
    record.lineno = 42
    record.funcName = "test_function"
    record.exc_info = None

    # Format the record
    result = formatter.format(record)

    # Parse JSON
    data = json.loads(result)

    # Check timestamp format (should be ISO 8601)
    assert data["timestamp"] == "2023-01-01T12:00:00Z"


def test_pydantic_import_error():
    """Test handling of missing Pydantic import."""
    formatter = StructuredFormatter()

    # Mock import error
    with patch("builtins.__import__", side_effect=ImportError("No module named 'pydantic'")):
        # Create a mock object pretending to be a Pydantic model
        class FakePydanticModel:
            def model_dump(self):
                return {"name": "test"}

        obj = FakePydanticModel()

        # Should fall back to str representation
        result = formatter._json_default(obj)
        assert isinstance(result, str)
