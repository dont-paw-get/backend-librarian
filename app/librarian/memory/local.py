"""로컬 인메모리 MemoryStore 구현.

개발/테스트용으로 프로세스 내 dict에 저장합니다.
프로세스 종료 시 데이터가 사라집니다.
AgentCore Runtime의 세션 수명 내에서는 충분합니다.
"""

from app.librarian.memory.base import ConversationEntry, MemoryStore, SessionContext


class LocalMemoryStore(MemoryStore):
    """인메모리 기반 세션 저장소."""

    def __init__(self, max_history: int = 20):
        self._store: dict[str, SessionContext] = {}
        self._max_history = max_history

    def _ensure_session(self, session_id: str) -> SessionContext:
        """세션이 없으면 새로 생성."""
        if session_id not in self._store:
            self._store[session_id] = SessionContext(session_id=session_id)
        return self._store[session_id]

    async def get_context(self, session_id: str) -> SessionContext:
        """세션의 대화 맥락과 선호 정보를 조회합니다."""
        return self._ensure_session(session_id)

    async def append_conversation(self, session_id: str, entry: ConversationEntry) -> None:
        """대화 기록을 추가합니다. max_history를 초과하면 오래된 것부터 제거."""
        ctx = self._ensure_session(session_id)
        ctx.history.append(entry)
        if len(ctx.history) > self._max_history:
            ctx.history = ctx.history[-self._max_history :]

    async def update_preferences(self, session_id: str, genres: list[str]) -> None:
        """선호 장르를 누적합니다. 중복 제거."""
        ctx = self._ensure_session(session_id)
        existing = set(ctx.preferred_genres)
        for genre in genres:
            if genre not in existing:
                ctx.preferred_genres.append(genre)
                existing.add(genre)
