"""Prometheus HTTP 메트릭 노출 (Micrometer 호환 이름).

infra(dpgy-infra)의 Prometheus 알림 규칙("HTTP 5xx 에러율", "p99 레이턴시")은
Spring Boot / Micrometer가 노출하는 `http_server_requests_seconds_*` 시계열을 기준으로
작성되어 있다. 이 서비스는 FastAPI(비-Spring)지만, 동일한 메트릭 이름·라벨을 그대로
노출해서 infra가 알림 규칙 쿼리를 수정하지 않아도 되도록 한다.

- `prometheus_client.Histogram("http_server_requests_seconds", ...)` 하나가
  `http_server_requests_seconds_bucket` / `_count` / `_sum` 시계열을 자동 파생한다.
  (`_bucket` 이 있어야 `histogram_quantile()` 기반 p99 알림이 동작한다.)
- `application` 라벨 = `OTEL_SERVICE_NAME` (메트릭 ↔ 로그 ↔ 트레이스 상관분석 키).
- `/actuator/prometheus` 로 노출한다 (ServiceMonitor가 이 경로를 스크레이핑).
- 헬스체크 / 스크레이핑 / k8s probe 경로는 메트릭에 기록하지 않는다
  (트레이스 probe 제외 정책과 동일 — tracing._EXCLUDED_URLS 참고).
"""

import os
import time

from prometheus_client import CONTENT_TYPE_LATEST, Histogram, generate_latest
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Micrometer가 `percentiles-histogram` 을 켰을 때 생성하는 버킷과 유사한 분포.
# Bedrock 호출이 포함된 요청은 수 초가 걸릴 수 있어 상단을 30s 까지 둔다.
_LATENCY_BUCKETS = (
    0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75,
    1.0, 2.0, 3.0, 5.0, 7.5, 10.0, 15.0, 30.0,
)

# 메트릭 자체 노출 경로 및 k8s probe / 헬스체크 경로 — 메트릭 집계에서 제외한다.
_EXCLUDED_PATHS = frozenset(
    {
        "/actuator/prometheus",
        "/metrics",
        "/health",
        "/api/v1/health",
        "/actuator/health",
        "/livez",
        "/readyz",
    }
)

# application 라벨 값. 프로세스 시작 시점(=import 시점)에 확정한다.
# tracing._build_resource() 의 service.name 과 반드시 같은 값이어야 상관분석이 된다.
_APPLICATION = os.environ.get("OTEL_SERVICE_NAME", "backend-librarian")

http_server_requests_seconds = Histogram(
    "http_server_requests_seconds",
    "HTTP server request latency in seconds (Micrometer-compatible)",
    labelnames=("application", "method", "uri", "status", "outcome"),
    buckets=_LATENCY_BUCKETS,
)


def _outcome(status: int) -> str:
    """HTTP 상태코드를 Micrometer 의 outcome 분류로 매핑한다."""
    if 100 <= status < 200:
        return "INFORMATIONAL"
    if 200 <= status < 300:
        return "SUCCESS"
    if 300 <= status < 400:
        return "REDIRECTION"
    if 400 <= status < 500:
        return "CLIENT_ERROR"
    return "SERVER_ERROR"


def _uri_label(path: str, status: int) -> str:
    """uri 라벨을 만든다.

    이 서비스의 라우트는 path 파라미터가 없어 원본 path 를 그대로 써도 카디널리티가
    폭증하지 않는다. 다만 매핑되지 않은 경로(스캐너 등)는 Micrometer 처럼
    "NOT_FOUND" 로 접어 카디널리티를 방어한다.
    """
    if status == 404:
        return "NOT_FOUND"
    return path or "/"


def _observe(method: str, path: str, status: int, elapsed_seconds: float) -> None:
    http_server_requests_seconds.labels(
        application=_APPLICATION,
        method=method,
        uri=_uri_label(path, status),
        status=str(status),
        outcome=_outcome(status),
    ).observe(elapsed_seconds)


class PrometheusMiddleware:
    """모든 HTTP 요청의 지연/상태코드를 Micrometer 호환 히스토그램에 기록하는 ASGI 미들웨어.

    `BaseHTTPMiddleware` 가 아니라 순수 ASGI 미들웨어로 구현해 StreamingResponse
    (stream=true 응답)와의 상호작용 문제를 피한다.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in _EXCLUDED_PATHS:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "")
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        start = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            _observe(method, path, 500, time.perf_counter() - start)
            raise
        _observe(method, path, status_code, time.perf_counter() - start)


def render_latest_metrics() -> Response:
    """`/actuator/prometheus` 응답 — 기본 레지스트리를 Prometheus 텍스트 포맷으로 직렬화한다."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
