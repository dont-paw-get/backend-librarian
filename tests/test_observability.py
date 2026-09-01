"""OpenTelemetry 트레이싱 및 구조화 JSON 로깅 검증.

핵심 검증 대상:
- OTEL_EXPORTER_OTLP_ENDPOINT 유무에 따른 exporter 활성화/비활성화
- 활성 span의 trace_id/span_id가 JSON 로그 필드에 정확히 반영되는지
- httpx 자동 계측을 통해 outbound 요청에 유효한 W3C traceparent가 자동 주입되는지
  (직접 헤더를 조립하지 않고 opentelemetry-instrumentation-httpx에 의해 주입됨)
- /health, /api/v1/health 가 FastAPI 자동 계측에서 제외되는지
"""

import json
import logging
import re

import httpx
import pytest
import respx
from opentelemetry import propagate, trace
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from app.librarian.observability.logging_setup import JsonFormatter
from app.librarian.observability.tracing import (
    _EXCLUDED_URLS,
    get_current_trace_ids,
    setup_tracing,
)

# W3C traceparent 형식: 00-<32자리 hex trace_id>-<16자리 hex span_id>-<2자리 flags>
_TRACEPARENT_RE = re.compile(r"^[0-9a-f]{2}-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")


@pytest.fixture(autouse=True)
def _isolate_otel_globals(monkeypatch):
    """각 테스트가 전역 TracerProvider/propagator를 독립적으로 갖도록 격리한다."""
    import app.librarian.observability.tracing as tracing_module

    monkeypatch.setattr(tracing_module, "_initialized", False)
    yield
    # httpx instrumentation은 전역 상태를 패치하므로 테스트 후 해제한다.
    if HTTPXClientInstrumentor().is_instrumented_by_opentelemetry:
        HTTPXClientInstrumentor().uninstrument()


class TestSetupTracing:
    def test_no_endpoint_does_not_raise_and_has_no_otlp_exporter(self, monkeypatch):
        """OTEL_EXPORTER_OTLP_ENDPOINT가 없으면 예외 없이 초기화되고 OTLP exporter가 붙지 않는다."""
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

        provider = setup_tracing()

        assert isinstance(provider, TracerProvider)
        # BatchSpanProcessor(OTLP)가 추가되지 않았는지 확인 — 내부 span_processor 목록이 비어있어야 함.
        processors = provider._active_span_processor._span_processors  # noqa: SLF001
        assert processors == ()

    def test_endpoint_set_enables_otlp_exporter(self, monkeypatch):
        """OTEL_EXPORTER_OTLP_ENDPOINT가 설정되면 OTLP exporter(BatchSpanProcessor)가 추가된다."""
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:14318")

        provider = setup_tracing()

        processors = provider._active_span_processor._span_processors  # noqa: SLF001
        assert len(processors) == 1

    def test_strands_redaction_env_is_forced(self, monkeypatch):
        """Strands Agent의 gen_ai 콘텐츠 redaction이 켜지도록 환경변수가 강제 설정된다."""
        monkeypatch.delenv("OTEL_SEMCONV_STABILITY_OPT_IN", raising=False)

        setup_tracing()

        assert "gen_ai_unredacted_attributes=" in __import__("os").environ["OTEL_SEMCONV_STABILITY_OPT_IN"]

    def test_health_urls_are_excluded(self):
        """/health, /api/v1/health가 FastAPI 자동 계측 제외 목록에 포함된다."""
        from opentelemetry.util.http import parse_excluded_urls

        excluded = parse_excluded_urls(_EXCLUDED_URLS)
        assert excluded.url_disabled("/health") is True
        assert excluded.url_disabled("/api/v1/health") is True
        assert excluded.url_disabled("/chat") is False
        assert excluded.url_disabled("/api/v1/chat") is False


class TestGetCurrentTraceIds:
    def test_no_active_span_returns_none(self):
        """활성 span이 없으면 (None, None)을 반환한다."""
        trace_id, span_id = get_current_trace_ids()
        assert trace_id is None
        assert span_id is None

    def test_active_span_returns_hex_ids(self):
        """활성 span이 있으면 32/16자리 16진수 문자열을 반환한다."""
        provider = TracerProvider()
        tracer = provider.get_tracer("test")

        with tracer.start_as_current_span("unit-test-span"):
            trace_id, span_id = get_current_trace_ids()

        assert trace_id is not None
        assert span_id is not None
        assert re.fullmatch(r"[0-9a-f]{32}", trace_id)
        assert re.fullmatch(r"[0-9a-f]{16}", span_id)


class TestJsonFormatter:
    def _make_record(self, **extra) -> logging.LogRecord:
        record = logging.LogRecord(
            name="app.librarian.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="테스트 메시지",
            args=(),
            exc_info=None,
        )
        for key, value in extra.items():
            setattr(record, key, value)
        return record

    def test_minimum_fields_present(self):
        """최소 필드(timestamp/level/service/logger/message/trace_id/span_id/exception)가 포함된다."""
        formatter = JsonFormatter(service_name="backend-librarian")
        record = self._make_record()

        payload = json.loads(formatter.format(record))

        for field in ("timestamp", "level", "service", "logger", "message", "trace_id", "span_id", "exception"):
            assert field in payload
        assert payload["service"] == "backend-librarian"
        assert payload["level"] == "INFO"
        assert payload["message"] == "테스트 메시지"

    def test_no_active_span_trace_fields_are_null(self):
        """활성 span이 없으면 trace_id/span_id가 null이다."""
        formatter = JsonFormatter(service_name="backend-librarian")
        record = self._make_record()

        payload = json.loads(formatter.format(record))

        assert payload["trace_id"] is None
        assert payload["span_id"] is None

    def test_active_span_populates_trace_fields(self):
        """활성 span이 있으면 trace_id/span_id가 로그 JSON에 채워진다."""
        provider = TracerProvider()
        tracer = provider.get_tracer("test")
        formatter = JsonFormatter(service_name="backend-librarian")

        with tracer.start_as_current_span("unit-test-span") as span:
            record = self._make_record()
            payload = json.loads(formatter.format(record))
            expected_trace_id = format(span.get_span_context().trace_id, "032x")
            expected_span_id = format(span.get_span_context().span_id, "016x")

        assert payload["trace_id"] == expected_trace_id
        assert payload["span_id"] == expected_span_id

    def test_extra_metadata_is_merged_without_raw_content(self):
        """logger.info(..., extra={...})로 넘긴 메타데이터가 JSON 필드로 병합된다."""
        formatter = JsonFormatter(service_name="backend-librarian")
        record = self._make_record(librarian_id="cat", mood="calm", switch_to=None)

        payload = json.loads(formatter.format(record))

        assert payload["librarian_id"] == "cat"
        assert payload["mood"] == "calm"
        assert payload["switch_to"] is None


class TestDownstreamTraceContextPropagation:
    """httpx 자동 계측을 통한 outbound traceparent 전파 검증.

    직접 traceparent 문자열을 조립하지 않고, opentelemetry-instrumentation-httpx가
    자동으로 W3C traceparent 헤더를 주입하는지 확인한다.
    """

    @pytest.fixture(autouse=True)
    def _setup_otel(self):
        provider = TracerProvider()
        exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        propagate.set_global_textmap(TraceContextTextMapPropagator())
        HTTPXClientInstrumentor().instrument()
        self.tracer = provider.get_tracer("test")
        self.exporter = exporter
        yield

    @pytest.mark.asyncio
    @respx.mock
    async def test_outbound_request_carries_valid_traceparent(self):
        """루트 span 안에서 나간 httpx 요청 헤더에 유효한 W3C traceparent가 자동 주입된다."""
        route = respx.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json={"current": {"temperature_2m": 20, "weather_code": 0}})
        )

        with self.tracer.start_as_current_span("root") as root_span:
            root_trace_id = format(root_span.get_span_context().trace_id, "032x")
            async with httpx.AsyncClient() as client:
                await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": 37.5665,
                        "longitude": 126.9780,
                        "current": "temperature_2m",
                        "timezone": "auto",
                    },
                )

        sent_traceparent = route.calls[0].request.headers.get("traceparent")
        assert sent_traceparent is not None
        assert _TRACEPARENT_RE.match(sent_traceparent), f"invalid traceparent format: {sent_traceparent}"

        # traceparent에 담긴 trace_id가 루트 span의 trace_id와 동일해야 같은 분산 Trace로 연결된다.
        _, carried_trace_id, _, _ = sent_traceparent.split("-")
        assert carried_trace_id == root_trace_id

    @pytest.mark.asyncio
    @respx.mock
    async def test_weather_provider_outbound_call_joins_same_trace(self):
        """OpenMeteoProvider(실제 애플리케이션 코드) 호출도 활성 trace에 편입된다."""
        from app.librarian.tools.weather import OpenMeteoProvider

        route = respx.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json={"current": {"temperature_2m": 18.0, "weather_code": 61}})
        )

        with self.tracer.start_as_current_span("root") as root_span:
            root_trace_id = format(root_span.get_span_context().trace_id, "032x")
            provider = OpenMeteoProvider()
            await provider.get_weather(37.5665, 126.9780)

        sent_traceparent = route.calls[0].request.headers.get("traceparent")
        assert sent_traceparent is not None
        _, carried_trace_id, _, _ = sent_traceparent.split("-")
        assert carried_trace_id == root_trace_id
