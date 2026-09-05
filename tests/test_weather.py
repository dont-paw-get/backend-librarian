"""날씨 도구 테스트 — Open-Meteo 응답 목킹으로 파싱 검증."""

import httpx
import pytest
import respx

from app.librarian.curation.mood import WeatherCondition
from app.librarian.tools.weather import (
    RAIN_THRESHOLD_MM,
    OpenMeteoProvider,
    WeatherResult,
    _wmo_to_condition,
    is_valid_coordinates,
    resolve_condition,
)


class TestIsValidCoordinates:
    @pytest.mark.parametrize(
        ("lat", "lon", "expected"),
        [
            (37.5665, 126.9780, True),  # 서울
            (0.0, 0.0, True),  # 적도/본초자오선
            (90.0, 180.0, True),  # 경계값 최대
            (-90.0, -180.0, True),  # 경계값 최소
            (90.1, 0.0, False),  # 위도 초과
            (-90.1, 0.0, False),  # 위도 미만
            (0.0, 180.1, False),  # 경도 초과
            (0.0, -180.1, False),  # 경도 미만
            (None, 126.0, False),  # 위도 없음
            (37.0, None, False),  # 경도 없음
            (None, None, False),  # 둘 다 없음
        ],
    )
    def test_validation(self, lat, lon, expected):
        assert is_valid_coordinates(lat, lon) is expected


class TestWmoToCondition:
    @pytest.mark.parametrize(
        ("code", "expected_condition"),
        [
            (0, WeatherCondition.CLEAR),
            (1, WeatherCondition.CLEAR),
            (3, WeatherCondition.CLOUDY),
            (45, WeatherCondition.FOGGY),
            (61, WeatherCondition.RAINY),
            (73, WeatherCondition.SNOWY),
            (95, WeatherCondition.STORMY),
            (999, WeatherCondition.CLOUDY),  # 알 수 없는 코드 → 중립값(흐림)
        ],
    )
    def test_code_mapping(self, code: int, expected_condition: WeatherCondition):
        condition, _ = _wmo_to_condition(code)
        assert condition == expected_condition

    def test_description_is_korean(self):
        _, desc = _wmo_to_condition(61)
        assert desc == "가벼운 비"


class TestResolveCondition:
    """WMO 코드 + 실측 강수량(mm) 병행 판정 검증."""

    def test_light_drizzle_below_threshold_is_downgraded_to_cloudy(self):
        """이슬비 코드(51)라도 강수량이 임계값 미만이면 CLOUDY로 강등한다."""
        condition, _ = resolve_condition(51, precipitation_mm=0.1)
        assert condition == WeatherCondition.CLOUDY

    def test_rain_at_or_above_threshold_stays_rainy(self):
        """강수량이 임계값 이상이면 RAINY를 유지한다."""
        condition, _ = resolve_condition(61, precipitation_mm=RAIN_THRESHOLD_MM)
        assert condition == WeatherCondition.RAINY

    def test_meaningful_rain_stays_rainy(self):
        """실제로 비가 오는 수준(보통 비)이면 RAINY."""
        condition, _ = resolve_condition(63, precipitation_mm=3.0)
        assert condition == WeatherCondition.RAINY

    def test_missing_precipitation_keeps_code_based_result(self):
        """강수량 정보가 없으면(None) 코드 기반 판정을 그대로 유지한다."""
        condition, _ = resolve_condition(61, precipitation_mm=None)
        assert condition == WeatherCondition.RAINY

    def test_non_rainy_code_is_not_affected_by_precipitation(self):
        """비 계열이 아닌 코드는 강수량과 무관하게 그대로 둔다."""
        clear, _ = resolve_condition(0, precipitation_mm=0.0)
        assert clear == WeatherCondition.CLEAR
        snowy, _ = resolve_condition(73, precipitation_mm=0.0)
        assert snowy == WeatherCondition.SNOWY


class TestOpenMeteoProvider:
    @pytest.mark.asyncio
    @respx.mock
    async def test_get_weather_success(self):
        """정상 응답 파싱 확인."""
        mock_response = {
            "current": {
                "temperature_2m": 18.5,
                "weather_code": 61,
            }
        }
        respx.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        async with httpx.AsyncClient() as client:
            provider = OpenMeteoProvider(client=client)
            result = await provider.get_weather(37.5665, 126.9780)

        assert isinstance(result, WeatherResult)
        assert result.temperature == 18.5
        assert result.condition == WeatherCondition.RAINY
        assert result.description == "가벼운 비"

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_weather_clear(self):
        """맑은 날씨 응답."""
        mock_response = {
            "current": {
                "temperature_2m": 25.0,
                "weather_code": 0,
            }
        }
        respx.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        async with httpx.AsyncClient() as client:
            provider = OpenMeteoProvider(client=client)
            result = await provider.get_weather(37.5665, 126.9780)

        assert result.condition == WeatherCondition.CLEAR
        assert result.temperature == 25.0

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_weather_http_error(self):
        """HTTP 오류 시 예외 발생."""
        respx.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(500)
        )

        async with httpx.AsyncClient() as client:
            provider = OpenMeteoProvider(client=client)
            with pytest.raises(httpx.HTTPStatusError):
                await provider.get_weather(37.5665, 126.9780)

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_weather_snowy(self):
        """눈 오는 날씨."""
        mock_response = {
            "current": {
                "temperature_2m": -2.0,
                "weather_code": 73,
            }
        }
        respx.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        async with httpx.AsyncClient() as client:
            provider = OpenMeteoProvider(client=client)
            result = await provider.get_weather(37.5665, 126.9780)

        assert result.condition == WeatherCondition.SNOWY
        assert result.temperature == -2.0

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_weather_light_drizzle_downgraded_by_precipitation(self):
        """이슬비 코드지만 실측 강수량이 미미하면 CLOUDY로 강등한다 (과분류 방지)."""
        mock_response = {
            "current": {
                "temperature_2m": 29.9,
                "weather_code": 51,  # 코드상 '가벼운 이슬비'
                "precipitation": 0.1,  # 실제로는 거의 안 옴
            }
        }
        respx.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        async with httpx.AsyncClient() as client:
            provider = OpenMeteoProvider(client=client)
            result = await provider.get_weather(37.4953, 127.1221)

        assert result.condition == WeatherCondition.CLOUDY
        assert result.temperature == 29.9

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_weather_real_rain_stays_rainy(self):
        """실제 강수량이 충분하면 RAINY를 유지한다."""
        mock_response = {
            "current": {
                "temperature_2m": 18.0,
                "weather_code": 63,  # 보통 비
                "precipitation": 3.2,
            }
        }
        respx.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        async with httpx.AsyncClient() as client:
            provider = OpenMeteoProvider(client=client)
            result = await provider.get_weather(37.5665, 126.9780)

        assert result.condition == WeatherCondition.RAINY

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_weather_uses_cache_for_nearby_coords(self):
        """동일 또는 약 1.1km 이내(소수점 2자리 반올림 일치) 좌표는 캐시를 사용하여 외부 API를 재호출하지 않는다."""
        mock_response = {
            "current": {
                "temperature_2m": 22.5,
                "weather_code": 0,
                "precipitation": 0.0,
            }
        }
        route = respx.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        async with httpx.AsyncClient() as client:
            provider = OpenMeteoProvider(client=client)
            # 첫 번째 호출
            res1 = await provider.get_weather(37.564, 126.974)
            # 아주 근접한 좌표 (소수점 2자리 반올림 시 37.56, 126.97 로 동일)
            res2 = await provider.get_weather(37.562, 126.971)

        assert res1 == res2
        # API는 1회만 호출되어야 함
        assert route.call_count == 1
