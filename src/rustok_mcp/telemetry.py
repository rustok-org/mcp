"""OpenTelemetry + structured-logging initialisation for the MCP server.

Always installs a JSON log handler on **stderr** (stdout carries the stdio
JSON-RPC framing, so logs must never go there). When ``RUSTOK_OTLP_ENDPOINT`` is
set, additionally exports spans over OTLP/HTTP to ``<endpoint>/v1/traces`` and
instruments httpx so MCP -> Gateway calls carry the W3C trace context — making a
request flowing MCP -> Gateway -> Core a single trace in Tempo.

Export is opt-in: with no endpoint (the default), only JSON logs are emitted —
no exporter is built and no network call is made. The default OTel propagator is
W3C ``tracecontext``, which FastAPI/httpx instrumentation use to extract/inject
``traceparent``.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_OTLP_ENDPOINT_ENV = "RUSTOK_OTLP_ENDPOINT"
_OTLP_TIMEOUT_SECONDS = 5.0

logger = logging.getLogger(__name__)

# Guards against double httpx instrumentation (re-import / repeated init in tests).
_httpx_instrumented = False


class TelemetryError(RuntimeError):
    """Invalid telemetry configuration — raised at startup to fail fast."""


def init_telemetry(service_name: str, log_level: str = "INFO") -> bool:
    """Configure JSON logging and, if an OTLP endpoint is set, tracing.

    Returns ``True`` when OTLP tracing was enabled (the caller should then
    instrument the FastAPI app), ``False`` for the JSON-logs-only path.

    Raises ``TelemetryError`` if ``RUSTOK_OTLP_ENDPOINT`` is set but malformed.
    """
    _configure_json_logging(log_level)

    endpoint = _resolve_endpoint()
    if endpoint is None:
        logger.info("telemetry: JSON logs only (%s unset)", _OTLP_ENDPOINT_ENV)
        return False

    _init_tracing(service_name, endpoint)
    return True


def _resolve_endpoint() -> str | None:
    """Return the validated OTLP base endpoint, or ``None`` for logs-only mode."""
    raw = os.environ.get(_OTLP_ENDPOINT_ENV, "").strip()
    if not raw:
        return None
    if not raw.startswith(("http://", "https://")):
        raise TelemetryError(
            f"invalid {_OTLP_ENDPOINT_ENV}: expected an http(s):// URL, got {_redact(raw)!r}"
        )
    return raw


def _init_tracing(service_name: str, endpoint: str) -> None:
    global _httpx_instrumented

    resource = Resource.create({"service.name": service_name})

    # The OTLP/HTTP exporters use the constructor ``endpoint`` verbatim (they do
    # not append the signal path), so build ``<base>/v1/{traces,metrics}``.
    base = endpoint.rstrip("/")
    traces_url = f"{base}/v1/traces"
    metrics_url = f"{base}/v1/metrics"

    provider = TracerProvider(resource=resource)
    # BatchSpanProcessor exports on a background thread — never on the request path.
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=traces_url, timeout=_OTLP_TIMEOUT_SECONDS))
    )
    trace.set_tracer_provider(provider)

    # Metrics: a PeriodicExportingMetricReader (background thread) pushes OTLP
    # metrics; the FastAPI/httpx instrumentation then auto-emits HTTP server/client
    # duration metrics against this global meter provider.
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=metrics_url, timeout=_OTLP_TIMEOUT_SECONDS)
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))

    if not _httpx_instrumented:
        HTTPXClientInstrumentor().instrument()
        _httpx_instrumented = True

    logger.info("telemetry: JSON logs + OTLP traces & metrics -> %s", _redact(base))


def _redact(url: str) -> str:
    """Strip ``user:pass@`` userinfo from a URL before logging it.

    Only an ``@`` inside the authority (before the first ``/``, ``?`` or ``#``)
    is userinfo; an ``@`` in the path/query is preserved.
    """
    scheme, sep, rest = url.partition("://")
    if not sep:
        return url
    cut = [pos for pos in (rest.find("/"), rest.find("?"), rest.find("#")) if pos != -1]
    authority_end = min(cut) if cut else len(rest)
    authority, tail = rest[:authority_end], rest[authority_end:]
    if "@" in authority:
        authority = authority.rpartition("@")[2]
    return f"{scheme}://{authority}{tail}"


def _configure_json_logging(log_level: str) -> None:
    """Route all logging through a single JSON handler on stderr.

    uvicorn is started with ``log_config=None`` (see ``main.run``) so its loggers
    propagate to the root handler installed here instead of uvicorn's own text
    formatter.
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonLogFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(log_level.upper())

    # uvicorn (when run with log_config=None) leaves these without handlers; make
    # them propagate to root so access/error logs are JSON too.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = []
        uv_logger.propagate = True


class _JsonLogFormatter(logging.Formatter):
    """Single-line JSON log records, enriched with the active trace/span ids."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            payload["trace_id"] = format(span_context.trace_id, "032x")
            payload["span_id"] = format(span_context.span_id, "016x")

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)
