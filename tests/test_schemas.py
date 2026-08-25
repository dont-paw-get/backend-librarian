"""스키마 유효성 검증 테스트."""

import pytest
from pydantic import ValidationError

from app.librarian.schemas import ChatRequest, ChatResponse, SwitchTo


class TestSwitchTo:
    def test_valid_switch_to(self):
        data = {"id": "stork", "name": "황새 사서", "icon": "🪿", "genres": ["미스터리", "판타지"]}
        switch = SwitchTo(**data)
        assert switch.id == "stork"
        assert switch.genres == ["미스터리", "판타지"]

    def test_empty_genres_is_valid(self):
        data = {"id": "cat", "name": "고양이 사서", "icon": "🐱", "genres": []}
        switch = SwitchTo(**data)
        assert switch.genres == []


class TestChatRequest:
    def test_valid_request(self):
        req = ChatRequest(
            message="비 오는 날 읽을 책 추천해줘",
            librarian_id="cat",
            session_id="sess-001",
        )
        assert req.latitude is None
        assert req.longitude is None

    def test_with_location(self):
        req = ChatRequest(
            message="오늘 날씨에 맞는 책",
            librarian_id="stork",
            session_id="sess-002",
            latitude=37.5665,
            longitude=126.9780,
        )
        assert req.latitude == 37.5665

    def test_empty_message_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="", librarian_id="cat", session_id="sess-001")

    def test_message_too_long_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="a" * 2001, librarian_id="cat", session_id="sess-001")


class TestChatResponse:
    def test_text_only_response(self):
        text = "좋은 책을 추천해줄게냥! 📚"
        resp = ChatResponse(message=text, session_id="sess-1", text=text)
        assert resp.switch_to is None

    def test_discovery_compatible_fields(self):
        """discovery 계약(message/session_id)과 text가 함께 제공됨."""
        text = "오늘은 에세이가 좋다냥 📖"
        resp = ChatResponse(message=text, session_id="sess-2", text=text)
        assert resp.message == resp.text
        assert resp.session_id == "sess-2"
        assert resp.librarian_id == "cat"

    def test_response_with_switch_to(self):
        text = "이건 황새 사서가 더 잘 알아냥~"
        resp = ChatResponse(
            message=text,
            session_id="sess-3",
            text=text,
            switch_to=SwitchTo(id="stork", name="황새 사서", icon="🪿", genres=["미스터리"]),
        )
        assert resp.switch_to is not None
        assert resp.switch_to.id == "stork"

    def test_serialization_to_dict(self):
        text = "안녕냥!"
        resp = ChatResponse(message=text, session_id="sess-4", text=text)
        data = resp.model_dump(exclude_none=True)
        assert data["text"] == text
        assert data["message"] == text
        assert data["session_id"] == "sess-4"
        assert "switch_to" not in data

    def test_serialization_with_switch_to(self):
        text = "넘길게냥~"
        resp = ChatResponse(
            message=text,
            session_id="sess-5",
            text=text,
            librarian_id="cat",
            switch_to=SwitchTo(id="stork", name="황새 사서", icon="🪿", genres=["SF"]),
        )
        data = resp.model_dump()
        assert data["switch_to"]["id"] == "stork"
        assert data["librarian_id"] == "cat"
