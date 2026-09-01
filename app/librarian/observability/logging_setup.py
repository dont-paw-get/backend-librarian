"""구조화 JSON 로깅 (stdout).

Kubernetes 환경에서는 stdout으로만 출력하고, Grafana Alloy가 이를 수집해 Loki로 전송한다.
Loki push client는 별도로 구현하지 않는다.

로그 레코드는 현재 활성 OpenTelemetry Span에서 trace_id/span_id를 읽어 JSON 필드로 포함시켜
Loki(로그) ↔ Tempo(트레이스) correlation을 가능하게 한다. trace_id/span_id는 Loki 라벨이 아니라
JSON 본문 필드로만 유지한다.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

from app.librarian.observability.tracing import get_current_trace_ids

_RESERVED_LOG_RECORD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """로그 레코드를 최소 필드를 갖춘 JSON 문자열로 직렬화한다.

    최소 필드: timestamp, level, service, logger, message, trace_id, span_id, exception
    활성 span이 없으면 trace_id/span_id는 null로 기록한다.
    """

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        trace_id, span_id = get_current_trace_ids()

        payload: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": self._service_name,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": trace_id,
            "span_id": span_id,
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        elif record.exc_text:
            payload["exception"] = record.exc_text
        else:
            payload["exception"] = None

        # logger.info("msg", extra={...})로 넘긴 추가 메타데이터(latency, downstream_service 등)를
        # 그대로 병합한다. 표준 LogRecord 속성과 겹치는 이름은 무시해 충돌을 피한다.
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_RECORD_ATTRS or key in payload:
                continue
            if key.startswith("_"):
                continue
            payload[key] = value

        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(service_name: str | None = None, level: str | None = None) -> None:
    """루트 로거에 stdout JSON 핸들러를 구성한다.

    여러 번 호출되어도 안전하다 (idempotent) — 기존 핸들러를 교체한다.

    Args:
        service_name: JSON 로그의 "service" 필드 값. 기본값은 OTEL_SERVICE_NAME 또는 "backend-librarian".
        level: 루트 로거 레벨. 기본값은 LOG_LEVEL 환경변수 또는 "INFO".
    """
    resolved_service_name = service_name or os.environ.get("OTEL_SERVICE_NAME", "backend-librarian")
    resolved_level = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter(resolved_service_name))

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(resolved_level)

    # uvicorn access log는 애플리케이션 INFO 로그와 별도 채널이므로 중복 기록을 피하기 위해
    # 레벨/포맷은 그대로 두되(운영자가 필요시 uvicorn 자체 로그를 참조), 애플리케이션 로거만
    # JSON 핸들러를 갖도록 한다. uvicorn.access는 propagate를 막아 루트 핸들러와 중복 출력되지
    # 않게 한다.
    logging.getLogger("uvicorn.access").propagate = False
