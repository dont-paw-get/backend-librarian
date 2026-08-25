"""AgentCore 엔트리포인트 — handle_chat.

전체 오케스트레이션 흐름:
1. 요청 파싱 및 검증
2. 세션 메모리에서 맥락 조회
3. 날씨 조회 (위치 정보가 있을 경우)
4. 무드 → 장르 매핑
5. 에이전트 호출 → 응답 생성
6. 메모리 업데이트
7. ChatResponse 반환
"""

from datetime import datetime, timezone
from uuid import uuid4

from app.librarian.curation.mood import WeatherCondition, recommend_genres
from app.librarian.librarians import get_librarian, get_other_librarian
from app.librarian.memory.base import ConversationEntry, MemoryStore
from app.librarian.schemas import ChatRequest, ChatResponse, SwitchTo
from app.librarian.tools.weather import WeatherProvider, WeatherResult


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
        weather_provider: 날씨 조회 프로바이더 (없으면 날씨 기반 추천 건너뜀)
        agent_callable: 에이전트 호출 함수 (테스트에서 fake로 대체 가능)
                        signature: (message: str, context: dict) -> str

    Returns:
        ChatResponse (text + optional switchTo)
    """
    # 1. 세션 ID 자동 생성 (프론트에서 안 보낸 경우)
    session_id = request.session_id or str(uuid4())

    # 2. 메모리에서 맥락 조회
    session_ctx = await memory.get_context(session_id)

    # 3. 날씨 조회 (위치 정보가 있을 경우, 또는 stork 사서면 기본 위치 사용)
    weather_result: WeatherResult | None = None
    latitude = request.latitude
    longitude = request.longitude

    # stork 사서인데 위치 정보가 없으면 기본 위치(서울) 사용
    if request.librarian_id == "stork" and latitude is None:
        latitude = 37.5665
        longitude = 126.9780

    if weather_provider and latitude is not None and longitude is not None:
        try:
            weather_result = await weather_provider.get_weather(latitude, longitude)
        except Exception:
            # 날씨 조회 실패해도 대화는 계속
            weather_result = None

    # 3. 무드 → 장르 매핑
    now = datetime.now(tz=timezone.utc)
    weather_condition = weather_result.condition if weather_result else WeatherCondition.CLEAR
    mood, recommended_genres = recommend_genres(now.hour, weather_condition)

    # 4. 담당 사서 확인 및 switchTo 판단
    current_librarian = get_librarian(request.librarian_id)
    other_librarian = get_other_librarian(request.librarian_id)
    switch_to: SwitchTo | None = None

    # 5. 에이전트 호출을 위한 맥락 조립
    context = {
        "session_history": [
            {"role": e.role, "content": e.content} for e in session_ctx.history[-10:]
        ],
        "preferred_genres": session_ctx.preferred_genres,
        "weather": {
            "condition": weather_condition.value,
            "temperature": weather_result.temperature if weather_result else None,
            "description": weather_result.description if weather_result else None,
        },
        "mood": mood.value,
        "recommended_genres": recommended_genres,
        "current_librarian": {
            "id": current_librarian.id if current_librarian else request.librarian_id,
            "specialties": current_librarian.specialties if current_librarian else [],
        },
    }

    # 6. 에이전트 호출
    if agent_callable:
        response_text = await agent_callable(request.message, context)
    else:
        # 실제 Strands 에이전트 호출 (이후 브랜치에서 구현)
        response_text = f"[에이전트 미연결] 메시지 수신: {request.message}"

    # 7. switchTo 판단 — 응답에 다른 사서 안내가 포함된 경우
    # 간단한 휴리스틱: 응답에 다른 사서 이름이 포함되면 switchTo 생성
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
        switch_to=switch_to,
    )
