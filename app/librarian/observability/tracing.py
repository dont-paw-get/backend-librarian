"""OpenTelemetry 분산 트레이싱 초기화.

설계 원칙:
- `OTEL_EXPORTER_OTLP_ENDPOINT`가 설정된 경우에만 OTLP exporter를 활성화한다.
  설정되지 않으면 (로컬 개발 등) TracerProvider만 구성하고 exporter는 붙이지 않으므로,
  Collector가 없는 환경에서도 애플리케이션은 정상적으로 시작/동작한다.
- 전역 TracerProvider를 설정하면 Strands Agent(`strands.telemetry.get_tracer()`)가
  자동으로 동일한 TracerProvider를 재사용하므로, agent 내부 span(`invoke_agent`, `chat`,
  `execute_event_loop_cycle` 등)이 별도 설정 없이 같은 Trace에 편입된다.
- exporter 전송 실패가 API 요청을 실패시키지 않도록, BatchSpanProcessor(비동기/버퍼링 전송)를
  사용하고 exporter 생성 자체도 예외를 삼켜 애플리케이션 기동을 막지 않는다.
"""

import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

_module_logger = logging.getLogger(__name__)

# 헬스체크/프로브 엔드포인트는 트레이스에서 제외한다 (FastAPI instrumentation의 excluded_urls).
_EXCLUDED_URLS = "health,/health,/api/v1/health"

# Strands Agent가 gen_ai.input.messages / gen_ai.output.messages / gen_ai.system_instructions 등
# prompt/response 원문을 span event에 기록하지 않도록 redaction을 강제로 켠다.
# (allowlist를 비워두면 모든 gen_ai 콘텐츠 속성이 "[REDACTED]" 로 대체된다.)
_STRANDS_REDACTION_ENV = "OTEL_SEMCONV_STABILITY_OPT_IN"
_STRANDS_REDACTION_TOKEN = "gen_ai_unredacted_attributes="

_initialized = False


def _ensure_strands_redaction_enabled() -> None:
    """Strands Agent의 gen_ai 콘텐츠 redaction이 켜지도록 환경변수를 보정한다.

    사용자가 이미 `OTEL_SEMCONV_STABILITY_OPT_IN`을 설정했다면 존중하되,
    redaction 토큰(`gen_ai_unredacted_attributes=...`)이 없으면 추가해준다.
    이 토큰이 전혀 없으면 strands의 Tracer._redaction_enabled가 False로 남아
    prompt/response 원문이 그대로 span에 노출되므로 반드시 필요하다.
    """
    current = os.environ.get(_STRANDS_REDACTION_ENV, "")
    tokens = [t.strip() for t in current.split(",") if t.strip()]
    if any(t.startswith("gen_ai_unredacted_attributes=") for t in tokens):
        return  # 사용자가 명시적으로 allowlist를 설정한 경우 그대로 존중
    tokens.append(_STRANDS_REDACTION_TOKEN)
    os.environ[_STRANDS_REDACTION_ENV] = ",".join(tokens)


def _build_resource() -> Resource:
    service_name = os.environ.get("OTEL_SERVICE_NAME", "backend-librarian")
    deployment_env = os.environ.get("DEPLOYMENT_ENV") or os.environ.get("ENVIRONMENT") or "local"
    return Resource.create(
        {
            "service.name": service_name,
            "deployment.environment": deployment_env,
        }
    )


def _build_sampler():
    ratio_raw = os.environ.get("OTEL_TRACES_SAMPLER_ARG", "1.0")
    try:
        ratio = float(ratio_raw)
    except ValueError:
        ratio = 1.0
    ratio = min(max(ratio, 0.0), 1.0)
    # ParentBased: 상위 서비스가 이미 샘플링 결정을 내렸다면(traceparent 전파) 그 결정을 따르고,
    # 루트 span일 때만 비율 샘플링을 적용한다. 분산 트레이스 일관성을 위해 필수.
    return ParentBased(TraceIdRatioBased(ratio))


def setup_tracing() -> TracerProvider:
    """OpenTelemetry TracerProvider를 초기화하고 전역으로 설정한다.

    `OTEL_EXPORTER_OTLP_ENDPOINT`가 설정된 경우에만 OTLP HTTP/protobuf exporter를 붙인다.
    설정되지 않으면 exporter 없는 TracerProvider만 전역으로 설정되어, 이후 계측 코드는
    동일하게 동작하지만 span은 아무 곳으로도 전송되지 않는다 (로컬 개발 지원).

    이 함수는 여러 번 호출되어도 안전하다 (idempotent) — 두 번째 호출부터는 아무 것도 하지 않는다.

    Returns:
        전역으로 설정된 TracerProvider.
    """
    global _initialized

    _ensure_strands_redaction_enabled()

    if _initialized:
        return trace.get_tracer_provider()

    resource = _build_resource()
    sampler = _build_sampler()
    provider = TracerProvider(resource=resource, sampler=sampler)

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        try:
            # OTLP HTTP/protobuf exporter. traces 전용 경로(/v1/traces)는
            # OTLPSpanExporter가 endpoint 뒤에 자동으로 덧붙인다.
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter()  # endpoint는 OTEL_EXPORTER_OTLP_ENDPOINT에서 자동 해석
            # BatchSpanProcessor는 백그라운드 스레드에서 배치 전송하며,
            # 전송 실패는 내부적으로 로깅만 하고 애플리케이션 요청 흐름에 영향을 주지 않는다.
            provider.add_span_processor(BatchSpanProcessor(exporter))
            _module_logger.info("OTLP trace exporter enabled endpoint=%s", endpoint)
        except Exception:  # noqa: BLE001 — exporter 구성 실패가 앱 기동을 막으면 안 됨
            _module_logger.exception("Failed to configure OTLP trace exporter; continuing without it")
    else:
        _module_logger.info("OTEL_EXPORTER_OTLP_ENDPOINT not set; tracing enabled without exporter")

    trace.set_tracer_provider(provider)
    # W3C Trace Context를 명시적으로 전파 포맷으로 설정 (traceparent 헤더).
    from opentelemetry import propagate

    propagate.set_global_textmap(TraceContextTextMapPropagator())

    _initialized = True
    return provider


def instrument_fastapi(app) -> None:
    """FastAPI 앱에 자동 계측을 적용한다. `/health` 등 프로브 엔드포인트는 제외한다."""
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app, excluded_urls=_EXCLUDED_URLS)


def instrument_httpx() -> None:
    """httpx 클라이언트에 자동 계측을 적용해 outbound 요청에 W3C traceparent를 자동 주입한다."""
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    HTTPXClientInstrumentor().instrument()


def instrument_botocore() -> None:
    """boto3/botocore 호출(Bedrock 등)에 자동 계측을 적용한다."""
    from opentelemetry.instrumentation.botocore import BotocoreInstrumentor

    BotocoreInstrumentor().instrument()


def get_current_trace_ids() -> tuple[str | None, str | None]:
    """현재 활성 Span의 trace_id/span_id를 16진수 문자열로 반환한다.

    활성 span이 없거나 유효하지 않으면 (None, None)을 반환한다.
    """
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx is None or not ctx.is_valid:
        return None, None
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")
