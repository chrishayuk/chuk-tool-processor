# tests/utils/test_fast_json.py
"""Tests for fast_json utilities."""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import pytest

# We'll test both with and without orjson by mocking the import
import chuk_tool_processor.utils.fast_json as fast_json


class TestFastJsonWithOrjson:
    """Test fast_json when orjson is available."""

    @pytest.fixture(autouse=True)
    def mock_orjson(self):
        """Ensure orjson path is tested."""
        # Save original state
        original_has_orjson = fast_json.HAS_ORJSON

        # Force orjson to be available
        with (
            patch.object(fast_json, "HAS_ORJSON", True),
            patch("chuk_tool_processor.utils.fast_json._orjson") as mock_orjson_module,
        ):
            # Setup mock orjson
            mock_orjson_module.dumps = MagicMock(side_effect=lambda obj, option=0: json.dumps(obj).encode("utf-8"))
            mock_orjson_module.loads = MagicMock(side_effect=lambda s: json.loads(s))
            mock_orjson_module.OPT_INDENT_2 = 1

            yield mock_orjson_module

        # Restore
        fast_json.HAS_ORJSON = original_has_orjson

    def test_dumps_basic(self, mock_orjson):
        """Test dumps with orjson."""
        result = fast_json.dumps({"key": "value"})
        assert result == '{"key": "value"}'
        mock_orjson.dumps.assert_called_once()

    def test_dumps_with_indent(self, mock_orjson):
        """Test dumps with indent option."""
        result = fast_json.dumps({"key": "value"}, indent=2)
        assert result == '{"key": "value"}'
        # Verify OPT_INDENT_2 was used
        call_args = mock_orjson.dumps.call_args
        assert call_args[1]["option"] == 1  # OPT_INDENT_2

    def test_dumps_fallback_on_error(self, mock_orjson):
        """Test dumps falls back to stdlib json on orjson error."""
        # Make orjson raise an exception
        mock_orjson.dumps.side_effect = TypeError("Unsupported type")

        result = fast_json.dumps({"key": "value"})
        assert result == '{"key": "value"}'

    def test_loads_basic(self, mock_orjson):
        """Test loads with orjson."""
        result = fast_json.loads('{"key": "value"}')
        assert result == {"key": "value"}
        mock_orjson.loads.assert_called_once()

    def test_loads_with_bytes(self, mock_orjson):
        """Test loads with bytes input."""
        result = fast_json.loads(b'{"key": "value"}')
        assert result == {"key": "value"}

    def test_loads_fallback_on_error(self, mock_orjson):
        """Test loads falls back to stdlib json on orjson error."""
        # Make orjson raise an exception
        mock_orjson.loads.side_effect = ValueError("Invalid JSON")

        # Test with string
        result = fast_json.loads('{"key": "value"}')
        assert result == {"key": "value"}

    def test_loads_fallback_with_bytes(self, mock_orjson):
        """Test loads fallback with bytes input."""
        # Make orjson raise an exception
        mock_orjson.loads.side_effect = ValueError("Invalid JSON")

        # Test with bytes - should decode and use stdlib json
        result = fast_json.loads(b'{"key": "value"}')
        assert result == {"key": "value"}

    def test_dump_basic(self, mock_orjson):
        """Test dump with orjson."""
        fp = io.BytesIO()
        fast_json.dump({"key": "value"}, fp)
        mock_orjson.dumps.assert_called_once()

    def test_dump_with_indent(self, mock_orjson):
        """Test dump with indent option."""
        fp = io.BytesIO()
        fast_json.dump({"key": "value"}, fp, indent=2)
        # Verify OPT_INDENT_2 was used
        call_args = mock_orjson.dumps.call_args
        assert call_args[1]["option"] == 1  # OPT_INDENT_2

    def test_dump_fallback_on_error(self, mock_orjson):
        """Test dump falls back to stdlib json on orjson error."""
        # Make orjson raise an exception
        mock_orjson.dumps.side_effect = TypeError("Unsupported type")

        fp = io.StringIO()
        fast_json.dump({"key": "value"}, fp)
        fp.seek(0)
        result = fp.read()
        assert result == '{"key": "value"}'

    def test_load_basic(self, mock_orjson):
        """Test load with orjson."""
        fp = io.StringIO('{"key": "value"}')
        result = fast_json.load(fp)
        assert result == {"key": "value"}
        mock_orjson.loads.assert_called_once()

    def test_load_fallback_on_error_seekable(self, mock_orjson):
        """Test load falls back to stdlib json on orjson error with seekable file."""
        # Make orjson raise an exception
        mock_orjson.loads.side_effect = ValueError("Invalid JSON")

        fp = io.StringIO('{"key": "value"}')
        result = fast_json.load(fp)
        assert result == {"key": "value"}

    def test_load_fallback_on_error_non_seekable(self, mock_orjson):
        """Test load fallback with non-seekable file."""
        # Make orjson raise an exception
        mock_orjson.loads.side_effect = ValueError("Invalid JSON")

        # Create a non-seekable file-like object
        class NonSeekable:
            def __init__(self, content):
                self.content = content
                self.pos = 0

            def read(self):
                result = self.content[self.pos :]
                self.pos = len(self.content)
                return result

        fp = NonSeekable('{"key": "value"}')
        result = fast_json.load(fp)
        assert result == {"key": "value"}

    def test_load_fallback_with_bytes(self, mock_orjson):
        """Test load fallback with bytes content."""
        # Make orjson raise an exception
        mock_orjson.loads.side_effect = ValueError("Invalid JSON")

        fp = io.BytesIO(b'{"key": "value"}')
        result = fast_json.load(fp)
        assert result == {"key": "value"}


class TestFastJsonWithoutOrjson:
    """Test fast_json when orjson is not available."""

    @pytest.fixture(autouse=True)
    def mock_no_orjson(self):
        """Force orjson to be unavailable."""
        # Save original state
        original_has_orjson = fast_json.HAS_ORJSON

        # Force orjson to be unavailable
        with patch.object(fast_json, "HAS_ORJSON", False):
            yield

        # Restore
        fast_json.HAS_ORJSON = original_has_orjson

    def test_dumps_without_orjson(self):
        """Test dumps without orjson uses stdlib json."""
        result = fast_json.dumps({"key": "value"})
        assert result == '{"key": "value"}'

    def test_dumps_with_indent_without_orjson(self):
        """Test dumps with indent without orjson."""
        result = fast_json.dumps({"key": "value"}, indent=2)
        assert '"key"' in result
        assert '"value"' in result

    def test_loads_without_orjson(self):
        """Test loads without orjson uses stdlib json."""
        result = fast_json.loads('{"key": "value"}')
        assert result == {"key": "value"}

    def test_loads_with_bytes_without_orjson(self):
        """Test loads with bytes without orjson."""
        result = fast_json.loads(b'{"key": "value"}')
        assert result == {"key": "value"}

    def test_dump_without_orjson(self):
        """Test dump without orjson uses stdlib json."""
        fp = io.StringIO()
        fast_json.dump({"key": "value"}, fp)
        fp.seek(0)
        result = fp.read()
        assert result == '{"key": "value"}'

    def test_load_without_orjson(self):
        """Test load without orjson uses stdlib json."""
        fp = io.StringIO('{"key": "value"}')
        result = fast_json.load(fp)
        assert result == {"key": "value"}


class TestJSONDecodeError:
    """Test JSONDecodeError export."""

    def test_jsondecode_error_import(self):
        """Test that JSONDecodeError is exported."""
        from chuk_tool_processor.utils.fast_json import JSONDecodeError

        # Verify it's the correct exception
        with pytest.raises(JSONDecodeError):
            json.loads("invalid json")

    def test_jsondecode_error_with_loads(self):
        """Test JSONDecodeError raised by loads."""
        with pytest.raises(fast_json.JSONDecodeError):
            fast_json.loads("invalid json")


class TestModuleExports:
    """Test module exports."""

    def test_all_exports(self):
        """Test that all expected exports are available."""
        assert hasattr(fast_json, "dumps")
        assert hasattr(fast_json, "loads")
        assert hasattr(fast_json, "dump")
        assert hasattr(fast_json, "load")
        assert hasattr(fast_json, "HAS_ORJSON")
        assert hasattr(fast_json, "JSONDecodeError")

        # Verify __all__
        assert "dumps" in fast_json.__all__
        assert "loads" in fast_json.__all__
        assert "dump" in fast_json.__all__
        assert "load" in fast_json.__all__
        assert "HAS_ORJSON" in fast_json.__all__
        assert "JSONDecodeError" in fast_json.__all__
