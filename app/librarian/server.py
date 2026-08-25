"""프론트 연동용 로컬 API 서버.

USE_BEDROCK=true 환경변수로 실제 Bedrock 에이전트와 fake 에이전트를 전환합니다.

실행:
    # fake 모드 (기본)
    uv run uvicorn app.librarian.server:app --reload

    # Bedrock 모드
    USE_BEDROCK=true uv run uvicorn app.librarian.server:app --reload
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.librarian.main import handle_chat
from app.librarian.memory.local import LocalMemoryStore
from app.librarian.schemas import ChatRequest, ChatResponse
from app.librarian.tools.weather import OpenMeteoProvider

# Bedrock 사용 여부
_USE_BEDROCK = os.environ.get("USE_BEDROCK", "").lower() in ("true", "1", "yes")

if _USE_BEDROCK:
    from app.librarian.bedrock_agent import bedrock_cat_agent, bedrock_stork_agent

    _AGENT_MAP = {"cat": bedrock_cat_agent, "stork": bedrock_stork_agent}
    _mode = "bedrock"
else:
    from app.librarian.fake_agent import fake_cat_agent, fake_stork_agent

    _AGENT_MAP = {"cat": fake_cat_agent, "stork": fake_stork_agent}
    _mode = "mock"

app = FastAPI(
    title="Don't Paw-get Your Book — Librarian API",
    description=f"사서 에이전트 API (mode: {_mode})",
    version="0.3.0",
)

# CORS — 프론트 로컬 개발 서버 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 싱글턴 인스턴스
_memory = LocalMemoryStore(max_history=50)
_weather = OpenMeteoProvider()


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """사서와 대화합니다."""
    agent = _AGENT_MAP.get(request.librarian_id, _AGENT_MAP["cat"])
    return await handle_chat(
        request=request,
        memory=_memory,
        weather_provider=_weather,
        agent_callable=agent,
    )


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_v1(request: ChatRequest) -> ChatResponse:
    """/chat과 동일 — 프론트/오케스트레이터 경로 컨벤션(/api/v1/) 대응."""
    return await chat(request)


@app.get("/health")
async def health():
    """헬스체크 엔드포인트."""
    return {"status": "ok", "mode": _mode}


@app.get("/api/v1/health")
async def health_v1():
    """헬스체크 — /api/v1/ 경로 별칭."""
    return await health()
