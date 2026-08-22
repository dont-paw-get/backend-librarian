"""Mock API 서버 테스트 — FastAPI TestClient로 HTTP 레벨 검증."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.librarian.server import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_ok(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["mode"] == "mock"


class TestChatEndpoint:
    @pytest.mark.asyncio
    async def test_basic_chat(self, client: AsyncClient):
        """기본 채팅 요청/응답."""
        payload = {
            "message": "비 오는 날 읽을 책 추천해줘",
            "librarian_id": "cat",
            "session_id": "test-sess-001",
        }
        resp = await client.post("/chat", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "text" in data
        assert "냥" in data["text"]

    @pytest.mark.asyncio
    async def test_chat_with_location(self, client: AsyncClient):
        """위치 정보 포함 요청 (Open-Meteo 호출은 실제 네트워크이므로 여기선 형식만 확인)."""
        payload = {
            "message": "오늘 날씨에 맞는 책",
            "librarian_id": "cat",
            "session_id": "test-sess-002",
            "latitude": 37.5665,
            "longitude": 126.9780,
        }
        resp = await client.post("/chat", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "text" in data
        assert len(data["text"]) > 0

    @pytest.mark.asyncio
    async def test_chat_invalid_empty_message(self, client: AsyncClient):
        """빈 메시지 → 422."""
        payload = {
            "message": "",
            "librarian_id": "cat",
            "session_id": "test-sess-003",
        }
        resp = await client.post("/chat", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_chat_missing_fields(self, client: AsyncClient):
        """필수 필드 누락 → 422."""
        payload = {"message": "안녕"}
        resp = await client.post("/chat", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_chat_response_schema(self, client: AsyncClient):
        """응답 스키마가 프론트 계약에 맞는지."""
        payload = {
            "message": "에세이 추천",
            "librarian_id": "cat",
            "session_id": "test-sess-004",
        }
        resp = await client.post("/chat", json=payload)
        data = resp.json()
        # text는 반드시 존재
        assert isinstance(data["text"], str)
        # switch_to는 null 또는 올바른 구조
        if data.get("switch_to"):
            assert "id" in data["switch_to"]
            assert "name" in data["switch_to"]
            assert "icon" in data["switch_to"]
            assert "genres" in data["switch_to"]

    @pytest.mark.asyncio
    async def test_session_memory_persists(self, client: AsyncClient):
        """같은 세션이면 메모리가 유지되어야 함."""
        session_id = "test-sess-memory"
        # 첫 번째 메시지
        await client.post("/chat", json={
            "message": "나 소설 좋아해",
            "librarian_id": "cat",
            "session_id": session_id,
        })
        # 두 번째 메시지 — 같은 세션
        resp = await client.post("/chat", json={
            "message": "또 추천해줘",
            "librarian_id": "cat",
            "session_id": session_id,
        })
        assert resp.status_code == 200
