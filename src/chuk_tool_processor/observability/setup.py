"""
Unified setup for OpenTelemetry observability.

Provides a single function to enable tracing and metrics.
"""

from __future__ import annotations

from chuk_tool_processor.logging import get_logger

from .metrics import init_metrics, start_metrics_server
from .tracing import init_tracer

logger = get_logger("chuk_tool_processor.observability.setup")


def setup_observability(
    *,
    service_name: str = "chuk-tool-processor",
    enable_tracing: bool = True,
    enable_metrics: bool = True,
    metrics_port: int = 9090,
    metrics_host: str = "0.0.0.0",  # nosec B104
) -> dict[str, bool]:
    """
    Setup OpenTelemetry tracing and Prometheus metrics.

    This is the main entry point for enabling observability in your application.

    Args:
        service_name: Service name for tracing
        enable_tracing: Enable OpenTelemetry tracing
        enable_metrics: Enable Prometheus metrics
        metrics_port: Port for Prometheus metrics server
        metrics_host: Host for Prometheus metrics server

    Returns:
        Dict with status of tracing and metrics initialization

    Example:
        from chuk_tool_processor.observability import setup_observability

        # Enable everything
        setup_observability(
            service_name="my-tool-service",
            enable_tracing=True,
            enable_metrics=True,
            metrics_port=9090
        )

        # Your tool execution is now automatically traced and instrumented!

    Environment Variables:
        - OTEL_EXPORTER_OTLP_ENDPOINT: OTLP endpoint (default: http://localhost:4317)
        - OTEL_SERVICE_NAME: Service name (overrides service_name parameter)
    """
    status = {
        "tracing_enabled": False,
        "metrics_enabled": False,
        "metrics_server_started": False,
    }

    # Initialize tracing
    if enable_tracing:
        try:
            tracer = init_tracer(service_name=service_name)
            status["tracing_enabled"] = tracer is not None
            logger.info(f"OpenTelemetry tracing enabled for '{service_name}'")
        except Exception as e:
            logger.error(f"Failed to initialize tracing: {e}")

    # Initialize metrics
    if enable_metrics:
        try:
            metrics = init_metrics()
            status["metrics_enabled"] = metrics is not None and metrics.enabled

            if status["metrics_enabled"]:
                # Start metrics server
                try:
                    start_metrics_server(port=metrics_port, host=metrics_host)
                    status["metrics_server_started"] = True
                    logger.info(f"Prometheus metrics available at http://{metrics_host}:{metrics_port}/metrics")
                except Exception as e:
                    logger.error(f"Failed to start metrics server: {e}")

        except Exception as e:
            logger.error(f"Failed to initialize metrics: {e}")

    # Log summary
    if status["tracing_enabled"] or status["metrics_enabled"]:
        features = []
        if status["tracing_enabled"]:
            features.append("tracing")
        if status["metrics_enabled"]:
            features.append("metrics")

        logger.info(f"Observability initialized: {', '.join(features)}")
    else:
        logger.warning(
            "Observability not initialized. Install dependencies:\n"
            "  pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp prometheus-client"
        )

    return status
