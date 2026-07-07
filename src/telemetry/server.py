"""HTTP server exposing Prometheus metrics on `/metrics`.

See OBSERVABILITY_AND_MONITORING.md ("Prometheus Exporters") and
`config/monitoring.yaml` for the feature toggle; the bind port itself is
connection configuration and therefore lives in the environment
(`PROMETHEUS_PORT`), per the project's env-vs-YAML convention.
"""

from __future__ import annotations

from prometheus_client import start_http_server

from src.common.logging import get_logger

_started = False


def start_metrics_server(port: int) -> None:
    """Start the Prometheus metrics HTTP server exactly once per process.

    Args:
        port: TCP port to bind the metrics server to.
    """
    global _started
    if _started:
        return
    start_http_server(port)
    get_logger(__name__).info("metrics_server_started", port=port)
    _started = True
