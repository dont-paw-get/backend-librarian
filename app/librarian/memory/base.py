"""MemoryStore 인터페이스 — 세션 기반 장기 메모리 추상화.

이후 구현체로 교체 가능:
- LocalMemoryStore (로컬 파일, 오늘 사용)
- AgentCoreMemoryStore (AWS AgentCore Memory)
- AuroraMemoryStore (팀 공용 Aurora DB)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ConversationEntry:
    """대화 기록 한 턴."""

    role: str  # "user" | "assistant"
    content: str
    timestamp: str  # ISO 8601


@dataclass
class SessionContext:
    """세션에서 조회되는 맥락 정보."""

    session_id: str
    history: list[ConversationEntry] = field(default_factory=list)
    preferred_genres: list[str] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)  # 임의 메타데이터


class MemoryStore(ABC):
    """메모리 저장소 인터페이스."""

    @abstractmethod
    async def get_context(self, session_id: str) -> SessionContext:
        """세션의 대화 맥락과 선호 정보를 조회합니다."""

    @abstractmethod
    async def append_conversation(self, session_id: str, entry: ConversationEntry) -> None:
        """대화 기록을 추가합니다."""

    @abstractmethod
    async def update_preferences(self, session_id: str, genres: list[str]) -> None:
        """선호 장르를 업데이트(누적)합니다."""
