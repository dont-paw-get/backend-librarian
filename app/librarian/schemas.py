"""요청/응답 스키마.

오케스트레이터(backend-discovery) 계약과 호환되도록 설계했습니다.
- 요청: message(필수) + session_id/librarian_id/stream(선택)
- 응답: message/session_id (discovery 호환) + text/switch_to + signals (librarian 고유)

signals: 우리 사서가 읽어낸 날씨·시간대·무드·장르포커스 정보.
팀원의 검색 에이전트가 이 정보를 활용해 실제 도서를 추천합니다.
"""

from typing import Literal

from pydantic import BaseModel, Field

LocationSource = Literal["user", "default_seoul", "text_stated", "none"]


class WeatherSignal(BaseModel):
    """날씨 시그널."""

    weather: str | None = Field(default=None, description="날씨 상태 (예: 비, 맑음, 눈)")
    condition: str | None = Field(default=None, description="날씨 상태 영문/국문 코드")
    temperature: float | None = Field(default=None, description="기온 (°C)")
    is_rainy: bool | None = Field(default=None, description="강수 여부")
    description: str | None = Field(default=None, description="날씨 설명")
    location_source: LocationSource | str | None = Field(
        default="none", description="위치 출처 (user, default_seoul, text_stated, none)"
    )
    confidence: float | None = Field(default=None, description="날씨 분석 신뢰도")


# 하위 호환용 별칭
WeatherInfo = WeatherSignal


class LibrarianSignals(BaseModel):
    """사서가 대화 및 상황 분석에서 도출한 시그널."""

    weather: WeatherSignal | None = Field(default=None, description="날씨 정보")
    time_of_day: str | None = Field(default=None, description="시간대 (dawn, day, evening, night 등)")
    mood: str | None = Field(default=None, description="사용자 감정/무드 키워드")
    genre_focus: list[str] | str = Field(default_factory=list, description="추천 포커스 장르")


# 하위 호환용 별칭
Signals = LibrarianSignals


class SwitchTo(BaseModel):
    """다른 사서에게 대화를 넘길 때 프론트에 전달하는 정보."""

    id: str = Field(description="사서 캐릭터 id (예: 'cat', 'stork')")
    name: str = Field(description="사서 이름 (예: '고양이 사서')")
    icon: str = Field(description="사서 아이콘 이모지")
    genres: list[str] = Field(description="해당 사서의 담당/특화 장르 목록")
    reason: str | None = Field(default=None, description="전환 추천 이유")


class ChatRequest(BaseModel):
    """채팅 요청 페이로드."""

    message: str = Field(min_length=1, max_length=2000, description="사용자 메시지")
    librarian_id: str = Field(default="cat", description="현재 대화 중인 사서 id")
    session_id: str | None = Field(default=None, description="세션 식별자 (없으면 자동 생성)")
    stream: bool = Field(default=False, description="스트리밍 응답 여부")
    latitude: float | None = Field(default=None, description="사용자 위치 위도")
    longitude: float | None = Field(default=None, description="사용자 위치 경도")


class ChatResponse(BaseModel):
    """채팅 응답.

    discovery 계약(message/session_id/signals/switch_to)과 librarian 고유 필드(text)를 함께 제공합니다.
    """

    message: str = Field(description="사서 답변 (discovery 호환 필드)")
    session_id: str = Field(description="세션 식별자")
    text: str = Field(description="사서 답변 (librarian 고유 필드, message와 동일)")
    librarian_id: str = Field(default="cat", description="응답한 사서 id")
    signals: LibrarianSignals | None = Field(default=None, description="날씨/시간/무드/장르포커스 신호")
    switch_to: SwitchTo | None = Field(default=None, description="다른 사서로 전환 시 정보")


