"""Telemetry init, endpoint validation, JSON logging, and httpx propagation."""

import json
import logging

import pytest
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider

import rustok_mcp.telemetry as telemetry
from rustok_mcp.telemetry import (
    TelemetryError,
    _JsonLogFormatter,
    _redact,
    _resolve_endpoint,
    init_telemetry,
)


@pytest.fixture(autouse=True)
def _restore_root_logging():
    """Telemetry init replaces the root logging handlers; restore them so the
    JSON config never leaks into other test modules (e.g. caplog)."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    yield
    root.handlers = saved_handlers
    root.setLevel(saved_level)


# httpx -> Gateway traceparent injection is OpenTelemetry's own instrumentation
# (HTTPXClientInstrumentor); it is exercised end-to-end by the live e2e
# (one MCP -> Gateway -> Core trace), not unit-tested here against OTel internals.

_ENV = "RUSTOK_OTLP_ENDPOINT"


def test_resolve_endpoint_unset_is_logs_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_ENV, raising=False)
    assert _resolve_endpoint() is None


def test_resolve_endpoint_blank_is_logs_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_ENV, "   ")
    assert _resolve_endpoint() is None


def test_resolve_endpoint_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_ENV, " http://alloy:4318 ")
    assert _resolve_endpoint() == "http://alloy:4318"


def test_resolve_endpoint_malformed_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_ENV, "alloy:4318")
    with pytest.raises(TelemetryError):
        _resolve_endpoint()


def test_init_telemetry_logs_only_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_ENV, raising=False)
    assert init_telemetry("rustok-mcp", "INFO") is False


def test_init_telemetry_enables_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    """With an endpoint set, tracing is enabled and httpx is instrumented."""
    monkeypatch.setenv(_ENV, "http://alloy:4318")
    monkeypatch.setattr(telemetry, "_httpx_instrumented", False)
    try:
        assert init_telemetry("rustok-mcp", "INFO") is True
        assert telemetry._httpx_instrumented is True
        assert HTTPXClientInstrumentor().is_instrumented_by_opentelemetry is True
    finally:
        HTTPXClientInstrumentor().uninstrument()
        telemetry._httpx_instrumented = False


def test_redact_strips_userinfo() -> None:
    assert _redact("https://token@collector:4318/v1/traces") == "https://collector:4318/v1/traces"
    assert _redact("https://u:p@c:4318") == "https://c:4318"
    # No userinfo / an '@' in the path or query is preserved.
    assert _redact("http://alloy:4318/v1/traces") == "http://alloy:4318/v1/traces"
    assert _redact("http://h:4318/p?x=a@b.com") == "http://h:4318/p?x=a@b.com"
    assert _redact("alloy:4318") == "alloy:4318"


def test_json_formatter_includes_trace_id() -> None:
    tracer = TracerProvider().get_tracer("test")
    formatter = _JsonLogFormatter()
    with tracer.start_as_current_span("op"):
        record = logging.LogRecord("rustok_mcp", logging.INFO, __file__, 1, "hello", None, None)
        line = formatter.format(record)

    payload = json.loads(line)  # valid JSON
    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    assert len(payload["trace_id"]) == 32
    assert len(payload["span_id"]) == 16
    assert "\x1b" not in line  # no ANSI


def test_json_formatter_without_span_omits_trace_id() -> None:
    formatter = _JsonLogFormatter()
    record = logging.LogRecord("rustok_mcp", logging.INFO, __file__, 1, "no span", None, None)
    payload = json.loads(formatter.format(record))
    assert "trace_id" not in payload
    assert payload["message"] == "no span"
