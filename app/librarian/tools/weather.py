"""날씨 조회 도구 — WeatherProvider 인터페이스 + OpenMeteo 구현.

Open-Meteo API는 무키(API 키 불필요)이며, WMO 날씨 코드를 반환합니다.
https://open-meteo.com/en/docs
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.librarian.curation.mood import WeatherCondition


@dataclass(frozen=True)
class WeatherResult:
    """날씨 조회 결과."""

    temperature: float  # 섭씨
    condition: WeatherCondition
    description: str  # 한국어 설명


class WeatherProvider(ABC):
    """날씨 조회 인터페이스 — 구현체 교체 가능."""

    @abstractmethod
    async def get_weather(self, latitude: float, longitude: float) -> WeatherResult:
        """주어진 좌표의 현재 날씨를 조회합니다."""


# === WMO 날씨 코드 → WeatherCondition 매핑 ===
# https://open-meteo.com/en/docs (WMO Weather interpretation codes)
_WMO_CODE_MAP: dict[int, tuple[WeatherCondition, str]] = {
    0: (WeatherCondition.CLEAR, "맑음"),
    1: (WeatherCondition.CLEAR, "대체로 맑음"),
    2: (WeatherCondition.CLOUDY, "부분적으로 흐림"),
    3: (WeatherCondition.CLOUDY, "흐림"),
    45: (WeatherCondition.FOGGY, "안개"),
    48: (WeatherCondition.FOGGY, "서리 안개"),
    51: (WeatherCondition.RAINY, "가벼운 이슬비"),
    53: (WeatherCondition.RAINY, "보통 이슬비"),
    55: (WeatherCondition.RAINY, "강한 이슬비"),
    56: (WeatherCondition.RAINY, "가벼운 얼어붙는 이슬비"),
    57: (WeatherCondition.RAINY, "강한 얼어붙는 이슬비"),
    61: (WeatherCondition.RAINY, "가벼운 비"),
    63: (WeatherCondition.RAINY, "보통 비"),
    65: (WeatherCondition.RAINY, "강한 비"),
    66: (WeatherCondition.RAINY, "가벼운 얼어붙는 비"),
    67: (WeatherCondition.RAINY, "강한 얼어붙는 비"),
    71: (WeatherCondition.SNOWY, "가벼운 눈"),
    73: (WeatherCondition.SNOWY, "보통 눈"),
    75: (WeatherCondition.SNOWY, "강한 눈"),
    77: (WeatherCondition.SNOWY, "싸락눈"),
    80: (WeatherCondition.RAINY, "가벼운 소나기"),
    81: (WeatherCondition.RAINY, "보통 소나기"),
    82: (WeatherCondition.STORMY, "강한 소나기"),
    85: (WeatherCondition.SNOWY, "가벼운 눈 소나기"),
    86: (WeatherCondition.SNOWY, "강한 눈 소나기"),
    95: (WeatherCondition.STORMY, "뇌우"),
    96: (WeatherCondition.STORMY, "가벼운 우박 뇌우"),
    99: (WeatherCondition.STORMY, "강한 우박 뇌우"),
}


def _wmo_to_condition(code: int) -> tuple[WeatherCondition, str]:
    """WMO 코드를 WeatherCondition과 한국어 설명으로 변환."""
    return _WMO_CODE_MAP.get(code, (WeatherCondition.CLEAR, "알 수 없음"))


# === 메시지 텍스트 → 날씨 감지 ===
# 사용자가 "비 오는 날 읽을 책"처럼 날씨를 직접 말하면 위치 없이도 반영합니다.
_TEXT_WEATHER_KEYWORDS: list[tuple[str, WeatherCondition]] = [
    ("장마", WeatherCondition.RAINY),
    ("소나기", WeatherCondition.RAINY),
    ("비", WeatherCondition.RAINY),
    ("눈", WeatherCondition.SNOWY),
    ("함박눈", WeatherCondition.SNOWY),
    ("맑", WeatherCondition.CLEAR),
    ("화창", WeatherCondition.CLEAR),
    ("흐린", WeatherCondition.CLOUDY),
    ("흐림", WeatherCondition.CLOUDY),
    ("구름", WeatherCondition.CLOUDY),
    ("안개", WeatherCondition.FOGGY),
    ("폭풍", WeatherCondition.STORMY),
    ("태풍", WeatherCondition.STORMY),
    ("천둥", WeatherCondition.STORMY),
    ("번개", WeatherCondition.STORMY),
]


def detect_weather_from_text(message: str) -> WeatherCondition | None:
    """메시지에 날씨 표현이 있으면 WeatherCondition으로 변환합니다.

    위치 정보 없이도 사용자가 언급한 날씨를 무드 매핑에 반영하기 위한 용도입니다.
    """
    for keyword, condition in _TEXT_WEATHER_KEYWORDS:
        if keyword in message:
            return condition
    return None


def is_valid_coordinates(latitude: float | None, longitude: float | None) -> bool:
    """좌표가 유효 범위(위도 -90~90, 경도 -180~180) 안에 있는지 확인합니다.

    둘 중 하나라도 None이거나 범위 밖이면 False.
    """
    if latitude is None or longitude is None:
        return False
    return -90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0


class OpenMeteoProvider(WeatherProvider):
    """Open-Meteo API 기반 날씨 조회 (무키, 무료)."""

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client

    async def get_weather(self, latitude: float, longitude: float) -> WeatherResult:
        """Open-Meteo에서 현재 날씨를 조회합니다."""
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,weather_code",
            "timezone": "auto",
        }

        if self._client:
            response = await self._client.get(self.BASE_URL, params=params)
        else:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.BASE_URL, params=params)

        response.raise_for_status()
        data = response.json()

        current = data["current"]
        temperature = current["temperature_2m"]
        weather_code = current["weather_code"]

        condition, description = _wmo_to_condition(weather_code)

        return WeatherResult(
            temperature=temperature,
            condition=condition,
            description=description,
        )
