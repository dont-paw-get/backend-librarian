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


# === 강수량 임계값 (mm, 직전 1시간 누적) ===
# Open-Meteo의 weather_code는 이슬비/가벼운 소나기(51/53/55/80 등)도 전부 "비"로
# 분류하므로, 코드만 신뢰하면 실제로는 거의 안 오는 이슬비도 RAINY가 된다.
# 기상 관측 표준상 이슬비(drizzle)는 강수율 약 1mm/h 이하이고, "약한 비(light rain)"의
# 하한도 대략 이 부근이다. 따라서 코드가 비 계열이어도 실측 강수량이 이 값 미만이면
# 실질 강수로 보지 않고 CLOUDY로 강등한다.
# 참고: Open-Meteo `precipitation`은 직전 1시간 누적(mm)이라 mm/h로 해석 가능하고,
# `precipitation_probability`(>0.1mm 기준)의 하한과도 정합적이다.
RAIN_THRESHOLD_MM = 0.5


def _wmo_to_condition(code: int) -> tuple[WeatherCondition, str]:
    """WMO 코드를 WeatherCondition과 한국어 설명으로 변환.

    미지의 코드는 CLEAR(맑음)로 낙관하지 않고 CLOUDY(흐림)로 처리한다.
    데이터가 없을 때 "맑음"으로 단정하면 실제 날씨와 어긋나 사서가 잘못된 안내를
    할 수 있으므로, 중립적인 "흐림"을 기본값으로 둔다.
    """
    return _WMO_CODE_MAP.get(code, (WeatherCondition.CLOUDY, "알 수 없음"))


def resolve_condition(
    weather_code: int, precipitation_mm: float | None
) -> tuple[WeatherCondition, str]:
    """WMO 코드와 실측 강수량(mm)을 함께 고려해 최종 날씨 상태를 결정한다.

    코드상 비(RAINY)로 분류됐더라도 실제 강수량이 이슬비 수준(RAIN_THRESHOLD_MM 미만)에
    그치면, 지나가는 이슬비/약한 소나기를 "비 오는 날"로 과장하지 않도록 CLOUDY로 강등한다.
    강수량 정보가 없으면(None) 기존 코드 기반 판정을 그대로 유지한다.
    """
    condition, description = _wmo_to_condition(weather_code)

    if (
        condition == WeatherCondition.RAINY
        and precipitation_mm is not None
        and precipitation_mm < RAIN_THRESHOLD_MM
    ):
        return WeatherCondition.CLOUDY, "구름 많음 (약한 비 기운)"

    return condition, description


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
            "current": "temperature_2m,weather_code,precipitation",
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
        # precipitation은 구버전 응답/일부 모델에서 누락될 수 있으므로 방어적으로 읽는다.
        precipitation = current.get("precipitation")

        condition, description = resolve_condition(weather_code, precipitation)

        return WeatherResult(
            temperature=temperature,
            condition=condition,
            description=description,
        )
