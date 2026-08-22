"""프론트 연동용 로컬 mock API 서버.

AgentCore Runtime 배포 전까지 프론트엔드 개발/테스트에 사용합니다.
프로덕션에서는 이 파일 대신 AgentCore Runtime 엔트리포인트가 역할을 대신합니다.

실행:
    uv run uvicorn app.librarian.server:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.librarian.fake_agent import fake_cat_agent
from app.librarian.main import handle_chat
from app.librarian.memory.local import LocalMemoryStore
from app.librarian.schemas import ChatRequest, ChatResponse
from app.librarian.tools.weather import OpenMeteoProvider

app = FastAPI(
    title="Don't Paw-get Your Book — Librarian API (Mock)",
    description="프론트 연동 테스트용 mock 서버. Bedrock 없이 fake 응답을 반환합니다.",
    version="0.1.0-mock",
)

# CORS — 프론트 로컬 개발 서버 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 싱글턴 인스턴스 (서버 수명 내 유지)
_memory = LocalMemoryStore(max_history=50)
_weather = OpenMeteoProvider()


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """사서와 대화합니다.

    fake 에이전트를 사용해 무드/장르 기반 고양이 말투 응답을 반환합니다.
    """
    return await handle_chat(
        request=request,
        memory=_memory,
        weather_provider=_weather,
        agent_callable=fake_cat_agent,
    )


@app.get("/health")
async def health():
    """헬스체크 엔드포인트."""
    return {"status": "ok", "mode": "mock"}
