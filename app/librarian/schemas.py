"""요청/응답 스키마.

오케스트레이터(backend-discovery) 계약과 호환되도록 설계했습니다.
- 요청: message(필수) + session_id/librarian_id/stream(선택)
- 응답: message/session_id (discovery 호환) + text/switch_to + signals (librarian 고유)

signals: 우리 사서가 읽어낸 날씨·시간대·무드·장르포커스 정보.
팀원의 검색 에이전트가 이 정보를 활용해 실제 도서를 추천합니다.
"""

from pydantic import BaseModel, Field


class SwitchTo(BaseModel):
    """다른 사서에게 대화를 넘길 때 프론트에 전달하는 정보."""

    id: str = Field(description="사서 캐릭터 id (예: 'cat', 'stork')")
    name: str = Field(description="사서 이름 (예: '고양이 사서')")
    icon: str = Field(description="사서 아이콘 이모지")
    genres: list[str] = Field(description="해당 사서의 특화 영역")


class WeatherInfo(BaseModel):
    """날씨 정보."""

    condition: str = Field(description="날씨 상태 (clear/cloudy/rainy/snowy/stormy/foggy)")
    temperature: float | None = Field(default=None, description="기온(섭씨), 좌표 기반 조회 시에만")
    description: str | None = Field(default=None, description="한국어 날씨 설명")


class Signals(BaseModel):
    """사서가 읽어낸 추천 신호 — 팀원 검색 에이전트가 활용."""

    weather: WeatherInfo | None = Field(default=None, description="날씨 정보")
    time_of_day: str = Field(description="시간대 (dawn/day/evening/night)")
    mood: str = Field(description="무드 (cozy/adventurous/reflective/dreamy/thrilling/calm)")
    genre_focus: str = Field(description="현재 사서의 특화 장르 (예: 미스터리, 비즈니스)")


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

    discovery 계약(message/session_id)과 librarian 고유 필드(text/switch_to/signals)를
    함께 제공해 프론트/오케스트레이터가 유연하게 파싱할 수 있게 합니다.
    """

    message: str = Field(description="사서 답변 (discovery 호환 필드)")
    session_id: str = Field(description="세션 식별자")
    text: str = Field(description="사서 답변 (librarian 고유 필드, message와 동일)")
    librarian_id: str = Field(default="cat", description="응답한 사서 id")
    signals: Signals | None = Field(default=None, description="날씨/시간/무드/장르포커스 신호")
    switch_to: SwitchTo | None = Field(default=None, description="다른 사서로 전환 시 정보")
