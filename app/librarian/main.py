"""AgentCore 오케스트레이션 엔트리포인트 — handle_chat.

전체 오케스트레이션 흐름:
1. 세션 ID 확보 및 메모리 맥락 조회
2. 날씨 파악 (메시지 텍스트 우선 → 좌표 조회 → 서울 기본값 폴백)
3. 시간대(KST 기준) 및 날씨 → 무드 매핑
4. signals 및 context 조립
5. 에이전트 호출 (페르소나 대화)
6. switch_to 다중 안전망 판단 ([전환제안: ...] 태그 및 별칭 감지)
7. 메모리 업데이트 후 ChatResponse 반환
"""

import logging
import re
from uuid import uuid4

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.librarian.curation.mood import (
    WeatherCondition,
    get_mood,
    hour_to_time_of_day,
    now_kst,
    recommend_genres,
)
from app.librarian.librarians import get_librarian, get_other_librarian
from app.librarian.memory.base import ConversationEntry, MemoryStore
from app.librarian.schemas import (
    ChatRequest,
    ChatResponse,
    LibrarianSignals,
    LocationSource,
    SwitchTo,
    WeatherSignal,
)
from app.librarian.tools.weather import (
    WeatherProvider,
    WeatherResult,
    detect_weather_from_text,
    is_valid_coordinates,
)

# 기본 위치 (서울) — 좌표/텍스트 날씨가 모두 없을 때 폴백
_DEFAULT_LAT = 37.5665
_DEFAULT_LON = 126.9780

# 전환 제안 태그 패턴
_SWITCH_TAG_PATTERN = re.compile(r"\[전환제안:\s*([a-zA-Z0-9_-]+)\]")

# 황새/슈빌 사서 식별 별칭
_STORK_ALIASES = ("황새 사서", "황새", "슈빌", "하루", "stork")
# 고양이 사서 식별 별칭
_CAT_ALIASES = ("고양이 사서", "고양이", "나비", "블루", "cat")

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)


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
        ChatResponse (message, text, session_id, librarian_id, switch_to, signals)
    """
    # 1. 세션 ID 확보
    session_id = request.session_id or str(uuid4())

    # 2. 메모리에서 맥락 조회
    session_ctx = await memory.get_context(session_id)

    # 3. 날씨 파악 (location_source 추적)
    weather_result: WeatherResult | None = None
    location_source: LocationSource = "none"
    stated_condition = detect_weather_from_text(request.message)

    if stated_condition is not None:
        # 3-1. 사용자가 메시지에 날씨를 직접 언급 → 우선 사용
        weather_condition = stated_condition
        location_source = "text_stated"
    else:
        # 3-2. 좌표가 유효하면 실제 날씨 조회, 없으면 서울 기본값 폴백
        latitude = request.latitude
        longitude = request.longitude
        has_user_coords = is_valid_coordinates(latitude, longitude)

        if has_user_coords:
            location_source = "user"
        elif request.librarian_id == "stork":
            latitude, longitude = _DEFAULT_LAT, _DEFAULT_LON
            location_source = "default_seoul"
        else:
            latitude = longitude = None
            location_source = "none"

        if weather_provider and latitude is not None and longitude is not None:
            try:
                weather_result = await weather_provider.get_weather(latitude, longitude)
            except Exception as exc:
                # 날씨 조회 실패해도 대화는 계속 — 기본(CLEAR) 날씨로 폴백한다.
                logger.warning(
                    "Weather lookup failed; falling back to default condition",
                    extra={"downstream_service": "open-meteo", "error_type": type(exc).__name__},
                )
                weather_result = None
                location_source = "none"

        weather_condition = weather_result.condition if weather_result else WeatherCondition.CLEAR
        if weather_result is None and not has_user_coords and request.librarian_id != "stork":
            location_source = "none"

    # 4. 시간대·날씨 → 무드 (KST 기준)
    now = now_kst()
    time_of_day_enum = hour_to_time_of_day(now.hour)
    mood = get_mood(time_of_day_enum, weather_condition)
    _, recommended_genres = recommend_genres(now.hour, weather_condition)

    # 5. 담당 사서 확인
    current_librarian = get_librarian(request.librarian_id)
    other_librarian = get_other_librarian(request.librarian_id)
    genre_focus = current_librarian.genre_focus if current_librarian else ""

    # 6. 에이전트 호출용 맥락
    context = {
        "session_history": [
            {"role": e.role, "content": e.content} for e in session_ctx.history[-10:]
        ],
        "preferred_genres": session_ctx.preferred_genres,
        "recommended_genres": recommended_genres,
        "weather": {
            "condition": weather_condition.value,
            "temperature": weather_result.temperature if weather_result else None,
            "description": weather_result.description if weather_result else None,
            "location_source": location_source,
        },
        "time_of_day": time_of_day_enum.value,
        "mood": mood.value,
        "genre_focus": genre_focus,
        "current_librarian": {
            "id": current_librarian.id if current_librarian else request.librarian_id,
            "specialties": current_librarian.specialties if current_librarian else [],
        },
    }

    # 7. 에이전트 호출
    # librarian.recommendation span: fake 모드(자동 계측 없음)에서도 agent 처리 구간(지연/실패)이
    # 관측 가능하도록 하는 상위 span. Bedrock 모드에서는 Strands가 자동 생성하는
    # `invoke_agent {agent_name}` span의 부모가 되어 오케스트레이션 관점의 latency를 함께 보여준다.
    if agent_callable:
        with _tracer.start_as_current_span("librarian.recommendation") as span:
            span.set_attribute("librarian.id", request.librarian_id)
            span.set_attribute("librarian.mood", mood.value)
            try:
                raw_response = await agent_callable(request.message, context)
                span.set_attribute("librarian.result_status", "ok")
            except Exception:
                span.set_attribute("librarian.result_status", "error")
                span.set_status(Status(StatusCode.ERROR))
                logger.error(
                    "Agent invocation failed",
                    extra={"librarian_id": request.librarian_id},
                    exc_info=True,
                )
                raise
    else:
        raw_response = f"[에이전트 미연결] 메시지 수신: {request.message}"

    # 8. switch_to 판단 및 태그 정제 (다중 안전망)
    target_id: str | None = None
    switch_to: SwitchTo | None = None

    # 8-1. 명시적 태그 [전환제안: stork/cat] 감지
    match = _SWITCH_TAG_PATTERN.search(raw_response)
    if match:
        target_id = match.group(1).strip().lower()
        response_text = _SWITCH_TAG_PATTERN.sub("", raw_response).strip()
    else:
        response_text = raw_response.strip()

    # 8-2. 태그가 없는 경우 다른 사서 이름/별칭 감지 (안전망)
    if not target_id and other_librarian:
        if request.librarian_id == "cat":
            if any(alias in response_text for alias in _STORK_ALIASES):
                target_id = "stork"
        else:  # stork
            if any(alias in response_text for alias in _CAT_ALIASES):
                target_id = "cat"

    # 8-3. switch_to 객체 조립
    if target_id and target_id != request.librarian_id:
        target_lib = get_librarian(target_id) or other_librarian
        if target_lib:
            switch_to = SwitchTo(
                id=target_lib.id,
                name=target_lib.name,
                icon=target_lib.icon,
                genres=target_lib.specialties,
                reason=f"{target_lib.name} 전문 분야 추천",
            )

    weather_desc = weather_result.description if weather_result else (
        stated_condition.value if stated_condition else None
    )
    weather_sig = WeatherSignal(
        weather=weather_desc,
        condition=weather_condition.value,
        temperature=weather_result.temperature if weather_result else None,
        description=weather_result.description if weather_result else None,
        is_rainy=weather_condition in (WeatherCondition.RAINY, WeatherCondition.STORMY),
        location_source=location_source,
    )

    signals = LibrarianSignals(
        weather=weather_sig,
        time_of_day=time_of_day_enum.value,
        mood=mood.value,
        genre_focus=genre_focus or recommended_genres,
    )

    # 10. 메모리 업데이트
    timestamp = now.isoformat()
    await memory.append_conversation(
        session_id,
        ConversationEntry(role="user", content=request.message, timestamp=timestamp),
    )
    await memory.append_conversation(
        session_id,
        ConversationEntry(role="assistant", content=response_text, timestamp=timestamp),
    )

    logger.info(
        "Chat request completed",
        extra={
            "librarian_id": request.librarian_id,
            "session_id": session_id,
            "mood": mood.value,
            "switch_to": switch_to.id if switch_to else None,
        },
    )

    return ChatResponse(
        message=response_text,
        session_id=session_id,
        text=response_text,
        librarian_id=request.librarian_id,
        signals=signals,
        switch_to=switch_to,
    )
