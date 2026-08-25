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
        """message만 보내도 기본값으로 정상 동작."""
        payload = {"message": "안녕"}
        resp = await client.post("/chat", json=payload)
        assert resp.status_code == 200

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
        # discovery 호환 필드 + librarian 고유 필드가 모두 존재
        assert isinstance(data["text"], str)
        assert data["message"] == data["text"]
        assert data["session_id"] == "test-sess-004"
        assert data["librarian_id"] == "cat"
        # switch_to는 null 또는 올바른 구조
        if data.get("switch_to"):
            assert "id" in data["switch_to"]
            assert "name" in data["switch_to"]
            assert "icon" in data["switch_to"]
            assert "genres" in data["switch_to"]

    @pytest.mark.asyncio
    async def test_session_id_auto_generated(self, client: AsyncClient):
        """session_id 미전달 시 서버가 자동 발급."""
        resp = await client.post("/chat", json={"message": "안녕"})
        data = resp.json()
        assert data["session_id"]

    @pytest.mark.asyncio
    async def test_api_v1_path(self, client: AsyncClient):
        """/api/v1/chat 경로도 동일하게 동작."""
        resp = await client.post(
            "/api/v1/chat",
            json={"message": "책 추천해줘", "librarian_id": "stork", "session_id": "v1-sess"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["librarian_id"] == "stork"
        assert data["session_id"] == "v1-sess"

    @pytest.mark.asyncio
    async def test_streaming_response(self, client: AsyncClient):
        """stream=true면 text/plain 스트리밍 + 세션 헤더."""
        resp = await client.post(
            "/api/v1/chat",
            json={"message": "책 추천해줘", "session_id": "stream-sess", "stream": True},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")
        assert resp.headers["x-session-id"] == "stream-sess"
        assert len(resp.text) > 0

    @pytest.mark.asyncio
    async def test_streaming_switch_to_header(self, client: AsyncClient):
        """switchTo 발생 시 X-Switch-To 헤더로 전달."""
        resp = await client.post(
            "/api/v1/chat",
            json={
                "message": "미스터리 소설 추천해줘",
                "librarian_id": "cat",
                "session_id": "stream-switch",
                "stream": True,
            },
        )
        assert resp.status_code == 200
        assert "x-switch-to" in resp.headers
        assert "stork" in resp.headers["x-switch-to"]

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
