"""메모리 추상화 + 로컬 구현 테스트."""

import pytest

from app.librarian.memory.base import ConversationEntry, SessionContext
from app.librarian.memory.local import LocalMemoryStore


@pytest.fixture
def store():
    return LocalMemoryStore(max_history=5)


class TestLocalMemoryStore:
    @pytest.mark.asyncio
    async def test_new_session_is_empty(self, store: LocalMemoryStore):
        ctx = await store.get_context("sess-new")
        assert ctx.session_id == "sess-new"
        assert ctx.history == []
        assert ctx.preferred_genres == []

    @pytest.mark.asyncio
    async def test_append_conversation(self, store: LocalMemoryStore):
        entry = ConversationEntry(role="user", content="안녕!", timestamp="2025-01-01T00:00:00Z")
        await store.append_conversation("sess-1", entry)

        ctx = await store.get_context("sess-1")
        assert len(ctx.history) == 1
        assert ctx.history[0].content == "안녕!"

    @pytest.mark.asyncio
    async def test_max_history_limit(self, store: LocalMemoryStore):
        """max_history=5를 초과하면 오래된 것부터 제거."""
        for i in range(8):
            entry = ConversationEntry(role="user", content=f"msg-{i}", timestamp=f"2025-01-01T{i:02d}:00:00Z")
            await store.append_conversation("sess-limit", entry)

        ctx = await store.get_context("sess-limit")
        assert len(ctx.history) == 5
        assert ctx.history[0].content == "msg-3"  # 0,1,2가 잘림
        assert ctx.history[-1].content == "msg-7"

    @pytest.mark.asyncio
    async def test_update_preferences(self, store: LocalMemoryStore):
        await store.update_preferences("sess-pref", ["소설", "에세이"])
        await store.update_preferences("sess-pref", ["에세이", "시"])  # 에세이 중복

        ctx = await store.get_context("sess-pref")
        assert ctx.preferred_genres == ["소설", "에세이", "시"]

    @pytest.mark.asyncio
    async def test_separate_sessions(self, store: LocalMemoryStore):
        """세션 간 데이터 격리."""
        entry_a = ConversationEntry(role="user", content="A", timestamp="2025-01-01T00:00:00Z")
        entry_b = ConversationEntry(role="user", content="B", timestamp="2025-01-01T00:00:00Z")
        await store.append_conversation("sess-a", entry_a)
        await store.append_conversation("sess-b", entry_b)

        ctx_a = await store.get_context("sess-a")
        ctx_b = await store.get_context("sess-b")
        assert len(ctx_a.history) == 1
        assert ctx_a.history[0].content == "A"
        assert ctx_b.history[0].content == "B"

    @pytest.mark.asyncio
    async def test_get_context_roundtrip(self, store: LocalMemoryStore):
        """저장 → 조회 라운드트립."""
        entry = ConversationEntry(role="assistant", content="추천이다냥!", timestamp="2025-01-01T12:00:00Z")
        await store.append_conversation("sess-rt", entry)
        await store.update_preferences("sess-rt", ["소설"])

        ctx = await store.get_context("sess-rt")
        assert isinstance(ctx, SessionContext)
        assert ctx.history[0].role == "assistant"
        assert "소설" in ctx.preferred_genres
