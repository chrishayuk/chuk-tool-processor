# chuk_tool_processor/utils/fast_json.py
"""
Fast JSON encoding/decoding with automatic fallback.

PERFORMANCE OPTIMIZED:
- Uses orjson if available (2-3x faster than stdlib json)
- Automatic fallback to stdlib json if orjson not installed
- Compatible API for seamless integration
"""

import json as _stdlib_json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Try to import orjson for 2-3x faster JSON operations
try:
    import orjson as _orjson

    HAS_ORJSON = True
    logger.debug("orjson available - using fast JSON implementation")
except ImportError:
    HAS_ORJSON = False
    logger.debug("orjson not available - using stdlib json")


def dumps(obj: Any, **kwargs: Any) -> str:
    """
    Serialize obj to a JSON formatted string.

    PERFORMANCE: Uses orjson if available (2-3x faster), falls back to stdlib json.

    Args:
        obj: Python object to serialize
        **kwargs: Additional arguments (for stdlib json compatibility)

    Returns:
        JSON string

    Note:
        orjson returns bytes, we decode to str for compatibility with existing code.
    """
    if HAS_ORJSON:
        # orjson.dumps returns bytes, decode to str for compatibility
        # orjson is ~2-3x faster than stdlib json
        try:
            # orjson options for compatibility with stdlib json
            # OPT_INDENT_2 for pretty printing if indent kwarg present
            options = 0
            if kwargs.get("indent"):
                options |= _orjson.OPT_INDENT_2

            return _orjson.dumps(obj, option=options).decode("utf-8")
        except Exception as e:
            # Fallback to stdlib json if orjson fails (e.g., unsupported types)
            logger.debug(f"orjson failed, falling back to stdlib json: {e}")
            return _stdlib_json.dumps(obj, **kwargs)
    else:
        # Use stdlib json
        return _stdlib_json.dumps(obj, **kwargs)


def loads(s: str | bytes) -> Any:
    """
    Deserialize s (a str, bytes or bytearray containing a JSON document) to a Python object.

    PERFORMANCE: Uses orjson if available (2-3x faster), falls back to stdlib json.

    Args:
        s: JSON string or bytes to deserialize

    Returns:
        Python object
    """
    if HAS_ORJSON:
        # orjson.loads accepts both str and bytes
        try:
            return _orjson.loads(s)
        except Exception as e:
            # Fallback to stdlib json if orjson fails
            logger.debug(f"orjson failed, falling back to stdlib json: {e}")
            if isinstance(s, bytes):
                s = s.decode("utf-8")
            return _stdlib_json.loads(s)
    else:
        # Use stdlib json
        if isinstance(s, bytes):
            s = s.decode("utf-8")
        return _stdlib_json.loads(s)


def dump(obj: Any, fp: Any, **kwargs: Any) -> None:
    """
    Serialize obj as a JSON formatted stream to fp (a .write()-supporting file-like object).

    PERFORMANCE: Uses orjson if available, falls back to stdlib json.

    Args:
        obj: Python object to serialize
        fp: File-like object with .write() method
        **kwargs: Additional arguments (for stdlib json compatibility)
    """
    if HAS_ORJSON:
        # orjson doesn't have dump(), so we use dumps() and write
        try:
            options = 0
            if kwargs.get("indent"):
                options |= _orjson.OPT_INDENT_2

            json_bytes = _orjson.dumps(obj, option=options)
            fp.write(json_bytes)
        except Exception as e:
            logger.debug(f"orjson failed, falling back to stdlib json: {e}")
            _stdlib_json.dump(obj, fp, **kwargs)
    else:
        _stdlib_json.dump(obj, fp, **kwargs)


def load(fp: Any) -> Any:
    """
    Deserialize fp (a .read()-supporting file-like object containing a JSON document) to a Python object.

    PERFORMANCE: Uses orjson if available, falls back to stdlib json.

    Args:
        fp: File-like object with .read() method

    Returns:
        Python object
    """
    if HAS_ORJSON:
        try:
            content = fp.read()
            return _orjson.loads(content)
        except Exception as e:
            logger.debug(f"orjson failed, falling back to stdlib json: {e}")
            # Re-read if needed
            if hasattr(fp, "seek"):
                fp.seek(0)
                content = fp.read()
            if isinstance(content, bytes):
                content = content.decode("utf-8")
            return _stdlib_json.loads(content)
    else:
        return _stdlib_json.load(fp)


# Export JSONDecodeError for compatibility
if HAS_ORJSON:
    # orjson uses the same JSONDecodeError from json module
    from json import JSONDecodeError
else:
    from json import JSONDecodeError

# Export flag for conditional behavior
__all__ = ["dumps", "loads", "dump", "load", "HAS_ORJSON", "JSONDecodeError"]
