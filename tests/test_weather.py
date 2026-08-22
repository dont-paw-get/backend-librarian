"""날씨 도구 테스트 — Open-Meteo 응답 목킹으로 파싱 검증."""

import httpx
import pytest
import respx

from app.librarian.curation.mood import WeatherCondition
from app.librarian.tools.weather import OpenMeteoProvider, WeatherResult, _wmo_to_condition


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
            (999, WeatherCondition.CLEAR),  # 알 수 없는 코드 → 기본값
        ],
    )
    def test_code_mapping(self, code: int, expected_condition: WeatherCondition):
        condition, _ = _wmo_to_condition(code)
        assert condition == expected_condition

    def test_description_is_korean(self):
        _, desc = _wmo_to_condition(61)
        assert desc == "가벼운 비"


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
