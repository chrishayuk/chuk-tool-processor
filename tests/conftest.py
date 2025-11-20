"""Global pytest configuration and fixtures."""

import sys

import pytest


@pytest.fixture(autouse=True, scope="function")
def reset_observability_state(request):
    """
    Reset observability module state before AND after each test to prevent test pollution.

    This is critical because many tests across different modules initialize
    observability (tracing/metrics) and the global state persists across tests.
    """
    # Reset BEFORE test
    try:
        # Force reimport to clear cached state
        if "chuk_tool_processor.observability.tracing" in sys.modules:
            import chuk_tool_processor.observability.tracing as tracing_module

            tracing_module._tracer = None
            tracing_module._tracing_enabled = False

        if "chuk_tool_processor.observability.metrics" in sys.modules:
            import chuk_tool_processor.observability.metrics as metrics_module

            metrics_module._metrics = None
            metrics_module._metrics_enabled = False
    except (ImportError, AttributeError):
        pass

    yield

    # Reset AFTER test as well
    try:
        if "chuk_tool_processor.observability.tracing" in sys.modules:
            import chuk_tool_processor.observability.tracing as tracing_module

            tracing_module._tracer = None
            tracing_module._tracing_enabled = False

        if "chuk_tool_processor.observability.metrics" in sys.modules:
            import chuk_tool_processor.observability.metrics as metrics_module

            metrics_module._metrics = None
            metrics_module._metrics_enabled = False
    except (ImportError, AttributeError):
        pass
