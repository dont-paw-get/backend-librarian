"""프론트엔드 계약과 1:1 대응하는 요청/응답 스키마."""

from pydantic import BaseModel, Field


class SwitchTo(BaseModel):
    """다른 사서에게 대화를 넘길 때 프론트에 전달하는 정보."""

    id: str = Field(description="사서 캐릭터 id (예: 'cat', 'stork')")
    name: str = Field(description="사서 이름 (예: '고양이 사서')")
    icon: str = Field(description="사서 아이콘 이모지")
    genres: list[str] = Field(description="해당 사서의 담당 장르 목록")


class ChatRequest(BaseModel):
    """채팅 요청 페이로드."""

    message: str = Field(min_length=1, max_length=2000, description="사용자 메시지")
    librarian_id: str = Field(description="현재 대화 중인 사서 id")
    session_id: str = Field(description="세션 식별자")
    latitude: float | None = Field(default=None, description="사용자 위치 위도")
    longitude: float | None = Field(default=None, description="사용자 위치 경도")


class ChatResponse(BaseModel):
    """채팅 응답 — 프론트 LibrarianChat 계약과 일치."""

    text: str = Field(description="사서 말투로 작성된 답변")
    switch_to: SwitchTo | None = Field(default=None, description="다른 사서로 전환 시 정보")
