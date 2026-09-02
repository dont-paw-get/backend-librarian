"""사서 에이전트 HTTP 서버.

오케스트레이터(backend-discovery) 및 프론트와의 계약:
- POST /api/v1/chat (별칭: /chat)
- 요청: {message, session_id?, librarian_id?, stream?, latitude?, longitude?}
- 응답(stream=false): {message, session_id, text, librarian_id, signals?, switch_to?}
- 응답(stream=true): text/plain 스트리밍 + X-Session-Id / X-Librarian-Id / X-Signals / X-Switch-To 헤더

USE_BEDROCK=true 환경변수로 실제 Bedrock 에이전트와 fake 에이전트를 전환합니다.

실행:
    # fake 모드 (기본, AWS 불필요)
    uv run uvicorn app.librarian.server:app --reload

    # Bedrock 모드 (MFA 세션 자격증명 필요)
    eval $(uv run python scripts/mfa_session.py <MFA코드>)
    USE_BEDROCK=true uv run uvicorn app.librarian.server:app --reload
"""

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.librarian.main import handle_chat
from app.librarian.memory.local import LocalMemoryStore
from app.librarian.observability.logging_setup import setup_logging
from app.librarian.observability.metrics import PrometheusMiddleware, render_latest_metrics
from app.librarian.observability.tracing import (
    instrument_botocore,
    instrument_fastapi,
    instrument_httpx,
    setup_tracing,
)
from app.librarian.schemas import ChatRequest, ChatResponse
from app.librarian.tools.weather import OpenMeteoProvider

# 로깅/트레이싱은 다른 모듈을 import하기 전, 프로세스 시작 시점에 가장 먼저 초기화한다.
# (Strands Agent가 이후 get_tracer()로 전역 TracerProvider를 재사용하므로 순서가 중요하다.)
setup_logging()
setup_tracing()
instrument_httpx()
instrument_botocore()

logger = logging.getLogger(__name__)

# Bedrock 사용 여부
_USE_BEDROCK = os.environ.get("USE_BEDROCK", "").lower() in ("true", "1", "yes")

if _USE_BEDROCK:
    from app.librarian.bedrock_agent import bedrock_cat_agent, bedrock_stork_agent, check_bedrock_access

    _AGENT_MAP = {"cat": bedrock_cat_agent, "stork": bedrock_stork_agent}
    _mode = "bedrock"
else:
    from app.librarian.fake_agent import fake_cat_agent, fake_stork_agent

    _AGENT_MAP = {"cat": fake_cat_agent, "stork": fake_stork_agent}
    _mode = "mock"
    check_bedrock_access = None

# 스트리밍 청크 크기 및 간격 (타이핑 효과)
_STREAM_CHUNK_SIZE = 12
_STREAM_DELAY_SECONDS = 0.02

@asynccontextmanager
async def _lifespan(_: FastAPI):
    """시작 시 Bedrock 자격증명 상태를 점검해 로그로 알립니다."""
    if _USE_BEDROCK and check_bedrock_access is not None:
        ok, detail = check_bedrock_access()
        if ok:
            logger.info("Bedrock access check succeeded", extra={"bedrock_detail": detail})
        else:
            logger.error(
                "Bedrock access check failed — MFA 세션 발급 필요 시 "
                "'uv run python scripts/mfa_session.py <MFA코드>' 실행 후 재시작하세요",
                extra={"bedrock_detail": detail},
            )
    else:
        logger.info("Running in mock mode (Bedrock disabled)")
    yield


app = FastAPI(
    title="Don't Paw-get Your Book — Librarian API",
    description=f"사서 에이전트 API (mode: {_mode})",
    version="0.4.0",
    lifespan=_lifespan,
)

# CORS — 프론트 로컬 개발 서버 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-Id", "X-Librarian-Id", "X-Switch-To", "X-Signals"],
)

# Prometheus HTTP 메트릭 미들웨어 — 모든 요청의 지연/상태코드를 Micrometer 호환
# 히스토그램(http_server_requests_seconds_*)에 기록한다. infra ServiceMonitor 가
# /actuator/prometheus 를 30s 간격으로 스크레이핑한다.
app.add_middleware(PrometheusMiddleware)

# FastAPI 자동 계측 — /health 등 프로브 엔드포인트는 트레이스에서 제외한다.
instrument_fastapi(app)

# 싱글턴 인스턴스
_memory = LocalMemoryStore(max_history=50)
_weather = OpenMeteoProvider()


async def _run_chat(request: ChatRequest) -> ChatResponse:
    """librarian_id에 맞는 에이전트로 오케스트레이션을 실행합니다."""
    agent = _AGENT_MAP.get(request.librarian_id, _AGENT_MAP["cat"])
    return await handle_chat(
        request=request,
        memory=_memory,
        weather_provider=_weather,
        agent_callable=agent,
    )


async def _stream_text(text: str) -> AsyncIterator[str]:
    """완성된 텍스트를 청크 단위로 흘려보냅니다 (타이핑 효과)."""
    for start in range(0, len(text), _STREAM_CHUNK_SIZE):
        yield text[start : start + _STREAM_CHUNK_SIZE]
        await asyncio.sleep(_STREAM_DELAY_SECONDS)


def _build_stream_headers(result: ChatResponse) -> dict[str, str]:
    """스트리밍 응답에 실어 보낼 메타데이터 헤더를 만듭니다.

    스트리밍 본문은 텍스트만 흘려보내므로, signals/switch_to 같은 구조화 데이터는
    헤더에 JSON 문자열(ASCII 이스케이프)로 실어 전달합니다.
    """
    headers = {
        "X-Session-Id": result.session_id,
        "X-Librarian-Id": result.librarian_id,
    }
    # 헤더 값은 ASCII만 안전하므로 ensure_ascii=True로 직렬화
    if result.signals:
        headers["X-Signals"] = json.dumps(
            result.signals.model_dump(exclude_none=True), ensure_ascii=True
        )
    if result.switch_to:
        headers["X-Switch-To"] = json.dumps(result.switch_to.model_dump(), ensure_ascii=True)
    return headers


async def _chat_endpoint(request: ChatRequest):
    """stream 플래그에 따라 JSON 또는 text/plain 스트리밍으로 응답합니다."""
    result = await _run_chat(request)

    if not request.stream:
        return result

    return StreamingResponse(
        _stream_text(result.text),
        media_type="text/plain; charset=utf-8",
        headers=_build_stream_headers(result),
    )


@app.post("/api/v1/chat")
async def chat_v1(request: ChatRequest):
    """사서와 대화합니다 (오케스트레이터/프론트 표준 경로)."""
    return await _chat_endpoint(request)


@app.post("/chat")
async def chat(request: ChatRequest):
    """/api/v1/chat 별칭 (prefix 없는 경로)."""
    return await _chat_endpoint(request)


@app.get("/api/v1/health")
async def health_v1():
    """헬스체크."""
    return {"status": "ok", "mode": _mode}


@app.get("/health")
async def health():
    """헬스체크 별칭."""
    return {"status": "ok", "mode": _mode}


@app.get("/actuator/prometheus")
async def actuator_prometheus():
    """Prometheus 스크레이핑 엔드포인트 (Micrometer 호환 경로).

    infra ServiceMonitor 가 이 경로를 스크레이핑한다. 응답에는
    http_server_requests_seconds_count / _bucket 시계열이 application="<OTEL_SERVICE_NAME>"
    라벨과 함께 포함된다.
    """
    return render_latest_metrics()
