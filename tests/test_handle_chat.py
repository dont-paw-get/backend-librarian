"""handle_chat 엔트리포인트 end-to-end 테스트 (fake 모델)."""

import pytest

from app.librarian.main import handle_chat
from app.librarian.memory.local import LocalMemoryStore
from app.librarian.schemas import ChatRequest


@pytest.fixture
def memory():
    return LocalMemoryStore()


class FakeWeatherProvider:
    """테스트용 날씨 프로바이더."""

    def __init__(self, temperature=18.0, condition="rainy", description="가벼운 비"):
        from app.librarian.curation.mood import WeatherCondition
        from app.librarian.tools.weather import WeatherResult

        self._result = WeatherResult(
            temperature=temperature,
            condition=WeatherCondition(condition),
            description=description,
        )

    async def get_weather(self, latitude: float, longitude: float):
        return self._result


async def fake_agent_normal(message: str, context: dict) -> str:
    """정상 응답을 생성하는 fake 에이전트."""
    mood = context.get("mood", "calm")
    genres = context.get("recommended_genres", [])
    genre_text = ", ".join(genres[:2]) if genres else "소설"
    return f"비 오는 날엔 {genre_text} 책이 딱이다냥 📖 오늘 무드는 {mood}이다냥~"


async def fake_agent_switch(message: str, context: dict) -> str:
    """다른 사서를 안내하는 fake 에이전트."""
    return "이 분야는 우리 황새 사서가 더 잘 알아냥~ 🪿 미스터리나 SF 쪽은 황새 사서한테 물어보라냥!"


class TestHandleChat:
    @pytest.mark.asyncio
    async def test_basic_response(self, memory: LocalMemoryStore):
        """기본 응답 생성."""
        request = ChatRequest(
            message="비 오는 날 읽을 책 추천해줘",
            librarian_id="cat",
            session_id="sess-test-1",
        )
        response = await handle_chat(
            request=request,
            memory=memory,
            agent_callable=fake_agent_normal,
        )
        assert response.text
        assert "냥" in response.text
        assert response.switch_to is None

    @pytest.mark.asyncio
    async def test_with_weather(self, memory: LocalMemoryStore):
        """날씨 정보가 포함된 요청."""
        request = ChatRequest(
            message="오늘 날씨에 맞는 책",
            librarian_id="cat",
            session_id="sess-test-2",
            latitude=37.5665,
            longitude=126.9780,
        )
        weather = FakeWeatherProvider(temperature=15.0, condition="rainy", description="보통 비")
        response = await handle_chat(
            request=request,
            memory=memory,
            weather_provider=weather,
            agent_callable=fake_agent_normal,
        )
        assert response.text
        assert "cozy" in response.text  # rainy → cozy mood

    @pytest.mark.asyncio
    async def test_switch_to_other_librarian(self, memory: LocalMemoryStore):
        """다른 사서 안내 시 switchTo가 포함됨."""
        request = ChatRequest(
            message="미스터리 소설 추천해줘",
            librarian_id="cat",
            session_id="sess-test-3",
        )
        response = await handle_chat(
            request=request,
            memory=memory,
            agent_callable=fake_agent_switch,
        )
        assert response.switch_to is not None
        assert response.switch_to.id == "stork"
        assert response.switch_to.name == "황새 사서"
        assert len(response.switch_to.genres) > 0

    @pytest.mark.asyncio
    async def test_memory_updated_after_chat(self, memory: LocalMemoryStore):
        """대화 후 메모리가 업데이트됨."""
        request = ChatRequest(
            message="안녕!",
            librarian_id="cat",
            session_id="sess-mem-test",
        )
        await handle_chat(
            request=request,
            memory=memory,
            agent_callable=fake_agent_normal,
        )
        ctx = await memory.get_context("sess-mem-test")
        assert len(ctx.history) == 2  # user + assistant
        assert ctx.history[0].role == "user"
        assert ctx.history[0].content == "안녕!"
        assert ctx.history[1].role == "assistant"

    @pytest.mark.asyncio
    async def test_weather_failure_does_not_break(self, memory: LocalMemoryStore):
        """날씨 조회 실패해도 대화는 정상 진행."""

        class FailingWeatherProvider:
            async def get_weather(self, lat, lon):
                raise ConnectionError("Network error")

        request = ChatRequest(
            message="책 추천해줘",
            librarian_id="cat",
            session_id="sess-fail-weather",
            latitude=37.5,
            longitude=127.0,
        )
        response = await handle_chat(
            request=request,
            memory=memory,
            weather_provider=FailingWeatherProvider(),
            agent_callable=fake_agent_normal,
        )
        assert response.text  # 정상 응답

    @pytest.mark.asyncio
    async def test_no_agent_callable_fallback(self, memory: LocalMemoryStore):
        """agent_callable이 없으면 폴백 메시지 반환."""
        request = ChatRequest(
            message="테스트",
            librarian_id="cat",
            session_id="sess-no-agent",
        )
        response = await handle_chat(
            request=request,
            memory=memory,
            agent_callable=None,
        )
        assert "에이전트 미연결" in response.text

    @pytest.mark.asyncio
    async def test_signals_included(self, memory: LocalMemoryStore):
        """응답에 signals(날씨/시간/무드/장르포커스)가 포함됨."""
        request = ChatRequest(
            message="안녕",
            librarian_id="cat",
            session_id="sess-signals",
        )
        response = await handle_chat(request=request, memory=memory, agent_callable=fake_agent_normal)
        assert response.signals is not None
        assert response.signals.genre_focus == "미스터리"
        assert response.signals.mood
        assert response.signals.time_of_day

    @pytest.mark.asyncio
    async def test_stated_weather_from_text(self, memory: LocalMemoryStore):
        """메시지에 날씨를 직접 언급하면 위치 없이도 반영."""
        request = ChatRequest(
            message="비 오는 날에 어울리는 분위기 알려줘",
            librarian_id="cat",
            session_id="sess-stated-weather",
        )
        response = await handle_chat(request=request, memory=memory, agent_callable=fake_agent_normal)
        assert response.signals is not None
        assert response.signals.weather is not None
        assert response.signals.weather.condition == "rainy"

    @pytest.mark.asyncio
    async def test_stork_genre_focus_business(self, memory: LocalMemoryStore):
        """stork의 genre_focus는 비즈니스."""
        request = ChatRequest(
            message="안녕하세요",
            librarian_id="stork",
            session_id="sess-stork-focus",
        )
        response = await handle_chat(request=request, memory=memory, agent_callable=fake_agent_normal)
        assert response.signals.genre_focus == "비즈니스"
