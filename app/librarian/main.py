"""오케스트레이션 엔트리포인트 — handle_chat.

흐름:
1. 세션 ID 확보
2. 메모리에서 맥락 조회
3. 날씨 파악 (메시지 텍스트 우선 → 좌표 조회 → 없으면 시간대만)
4. 시간대·날씨 → 무드 매핑
5. signals 조립 (팀원 검색 에이전트가 활용)
6. 에이전트 호출 (페르소나 대화, 실제 도서 추천은 하지 않음)
7. switchTo 판단
8. 메모리 업데이트 후 ChatResponse 반환
"""

from datetime import datetime, timezone
from uuid import uuid4

from app.librarian.curation.mood import (
    WeatherCondition,
    get_mood,
    hour_to_time_of_day,
)
from app.librarian.librarians import get_librarian, get_other_librarian
from app.librarian.memory.base import ConversationEntry, MemoryStore
from app.librarian.schemas import ChatRequest, ChatResponse, Signals, SwitchTo, WeatherInfo
from app.librarian.tools.weather import (
    WeatherProvider,
    WeatherResult,
    detect_weather_from_text,
    is_valid_coordinates,
)

# stork 사서 기본 위치 (서울) — 좌표/텍스트 날씨가 모두 없을 때 폴백
_DEFAULT_LAT = 37.5665
_DEFAULT_LON = 126.9780


async def handle_chat(
    request: ChatRequest,
    memory: MemoryStore,
    weather_provider: WeatherProvider | None = None,
    agent_callable=None,
) -> ChatResponse:
    """채팅 요청을 처리하고 응답을 반환합니다.

    Args:
        request: 검증된 채팅 요청
        memory: 메모리 저장소 인스턴스
        weather_provider: 날씨 조회 프로바이더
        agent_callable: 에이전트 호출 함수 (테스트에서 fake로 대체 가능)
                        signature: (message: str, context: dict) -> str

    Returns:
        ChatResponse (text + signals + optional switchTo)
    """
    # 1. 세션 ID 확보
    session_id = request.session_id or str(uuid4())

    # 2. 메모리에서 맥락 조회
    session_ctx = await memory.get_context(session_id)

    # 3. 날씨 파악
    weather_result: WeatherResult | None = None
    stated_condition = detect_weather_from_text(request.message)

    if stated_condition is not None:
        # 3-1. 사용자가 메시지에 날씨를 직접 언급 → 우선 사용 (위치 불필요)
        weather_condition = stated_condition
    else:
        # 3-2. 좌표가 유효하면 실제 날씨 조회. 범위 밖이면 무시하고 폴백.
        latitude = request.latitude
        longitude = request.longitude
        if not is_valid_coordinates(latitude, longitude):
            latitude = longitude = None  # 유효하지 않은 좌표는 버림

        # stork는 좌표가 없으면 서울 기본 위치 폴백
        if request.librarian_id == "stork" and latitude is None:
            latitude, longitude = _DEFAULT_LAT, _DEFAULT_LON

        if weather_provider and latitude is not None and longitude is not None:
            try:
                weather_result = await weather_provider.get_weather(latitude, longitude)
            except Exception:
                weather_result = None

        weather_condition = weather_result.condition if weather_result else WeatherCondition.CLEAR

    # 4. 시간대·날씨 → 무드
    now = datetime.now(tz=timezone.utc)
    time_of_day = hour_to_time_of_day(now.hour)
    mood = get_mood(time_of_day, weather_condition)

    # 5. 담당 사서 및 signals 조립
    current_librarian = get_librarian(request.librarian_id)
    other_librarian = get_other_librarian(request.librarian_id)
    genre_focus = current_librarian.genre_focus if current_librarian else ""

    weather_info = WeatherInfo(
        condition=weather_condition.value,
        temperature=weather_result.temperature if weather_result else None,
        description=weather_result.description if weather_result else None,
    )
    signals = Signals(
        weather=weather_info,
        time_of_day=time_of_day.value,
        mood=mood.value,
        genre_focus=genre_focus,
    )

    # 에이전트 호출용 맥락
    context = {
        "session_history": [
            {"role": e.role, "content": e.content} for e in session_ctx.history[-10:]
        ],
        "preferred_genres": session_ctx.preferred_genres,
        "weather": weather_info.model_dump(),
        "time_of_day": time_of_day.value,
        "mood": mood.value,
        "genre_focus": genre_focus,
        "current_librarian": {
            "id": current_librarian.id if current_librarian else request.librarian_id,
            "specialties": current_librarian.specialties if current_librarian else [],
        },
    }

    # 6. 에이전트 호출
    if agent_callable:
        response_text = await agent_callable(request.message, context)
    else:
        response_text = f"[에이전트 미연결] 메시지 수신: {request.message}"

    # 7. switchTo 판단 — 응답에 다른 사서 이름이 포함되면 전환 신호 생성
    switch_to: SwitchTo | None = None
    if other_librarian and other_librarian.name in response_text:
        switch_to = SwitchTo(
            id=other_librarian.id,
            name=other_librarian.name,
            icon=other_librarian.icon,
            genres=other_librarian.specialties,
        )

    # 8. 메모리 업데이트
    timestamp = now.isoformat()
    await memory.append_conversation(
        session_id,
        ConversationEntry(role="user", content=request.message, timestamp=timestamp),
    )
    await memory.append_conversation(
        session_id,
        ConversationEntry(role="assistant", content=response_text, timestamp=timestamp),
    )

    return ChatResponse(
        message=response_text,
        session_id=session_id,
        text=response_text,
        librarian_id=request.librarian_id,
        signals=signals,
        switch_to=switch_to,
    )
