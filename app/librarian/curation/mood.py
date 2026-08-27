"""시간대·날씨 → 무드 → 장르 매핑 로직.

순수 함수로 구현하여 외부 의존 없이 단위 테스트 가능.
시간대는 한국 표준시(KST, Asia/Seoul) 기준으로 계산합니다.
"""

from datetime import datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

# 서비스 기준 타임존 (한국). 해외 확장 시 좌표 기반 타임존으로 교체 가능.
KST = ZoneInfo("Asia/Seoul")


class TimeOfDay(StrEnum):
    """하루를 4구간으로 분류."""

    DAWN = "dawn"  # 05:00 ~ 08:59
    DAY = "day"  # 09:00 ~ 16:59
    EVENING = "evening"  # 17:00 ~ 20:59
    NIGHT = "night"  # 21:00 ~ 04:59


class WeatherCondition(StrEnum):
    """날씨 상태를 대분류로 정규화."""

    CLEAR = "clear"
    CLOUDY = "cloudy"
    RAINY = "rainy"
    SNOWY = "snowy"
    STORMY = "stormy"
    FOGGY = "foggy"


class Mood(StrEnum):
    """날씨+시간대 조합으로 결정되는 독서 무드."""

    COZY = "cozy"  # 아늑한, 따뜻한
    ADVENTUROUS = "adventurous"  # 모험적인, 활동적인
    REFLECTIVE = "reflective"  # 사색적인, 내향적인
    DREAMY = "dreamy"  # 몽환적인, 감성적인
    THRILLING = "thrilling"  # 스릴 있는, 긴장감
    CALM = "calm"  # 평온한, 여유로운


def hour_to_time_of_day(hour: int) -> TimeOfDay:
    """0~23시를 TimeOfDay로 변환합니다."""
    if 5 <= hour <= 8:
        return TimeOfDay.DAWN
    elif 9 <= hour <= 16:
        return TimeOfDay.DAY
    elif 17 <= hour <= 20:
        return TimeOfDay.EVENING
    else:
        return TimeOfDay.NIGHT


def now_kst() -> datetime:
    """현재 시각을 KST(Asia/Seoul) 기준으로 반환합니다."""
    return datetime.now(tz=KST)


def current_time_of_day() -> TimeOfDay:
    """현재 KST 시각 기준의 시간대를 반환합니다."""
    return hour_to_time_of_day(now_kst().hour)


# === 무드 매핑 테이블 ===
# (시간대, 날씨) → 무드
_MOOD_TABLE: dict[tuple[TimeOfDay, WeatherCondition], Mood] = {
    # 새벽
    (TimeOfDay.DAWN, WeatherCondition.CLEAR): Mood.CALM,
    (TimeOfDay.DAWN, WeatherCondition.CLOUDY): Mood.REFLECTIVE,
    (TimeOfDay.DAWN, WeatherCondition.RAINY): Mood.COZY,
    (TimeOfDay.DAWN, WeatherCondition.SNOWY): Mood.DREAMY,
    (TimeOfDay.DAWN, WeatherCondition.STORMY): Mood.THRILLING,
    (TimeOfDay.DAWN, WeatherCondition.FOGGY): Mood.DREAMY,
    # 낮
    (TimeOfDay.DAY, WeatherCondition.CLEAR): Mood.ADVENTUROUS,
    (TimeOfDay.DAY, WeatherCondition.CLOUDY): Mood.CALM,
    (TimeOfDay.DAY, WeatherCondition.RAINY): Mood.COZY,
    (TimeOfDay.DAY, WeatherCondition.SNOWY): Mood.DREAMY,
    (TimeOfDay.DAY, WeatherCondition.STORMY): Mood.THRILLING,
    (TimeOfDay.DAY, WeatherCondition.FOGGY): Mood.REFLECTIVE,
    # 저녁
    (TimeOfDay.EVENING, WeatherCondition.CLEAR): Mood.CALM,
    (TimeOfDay.EVENING, WeatherCondition.CLOUDY): Mood.REFLECTIVE,
    (TimeOfDay.EVENING, WeatherCondition.RAINY): Mood.COZY,
    (TimeOfDay.EVENING, WeatherCondition.SNOWY): Mood.COZY,
    (TimeOfDay.EVENING, WeatherCondition.STORMY): Mood.THRILLING,
    (TimeOfDay.EVENING, WeatherCondition.FOGGY): Mood.DREAMY,
    # 밤
    (TimeOfDay.NIGHT, WeatherCondition.CLEAR): Mood.REFLECTIVE,
    (TimeOfDay.NIGHT, WeatherCondition.CLOUDY): Mood.DREAMY,
    (TimeOfDay.NIGHT, WeatherCondition.RAINY): Mood.COZY,
    (TimeOfDay.NIGHT, WeatherCondition.SNOWY): Mood.DREAMY,
    (TimeOfDay.NIGHT, WeatherCondition.STORMY): Mood.THRILLING,
    (TimeOfDay.NIGHT, WeatherCondition.FOGGY): Mood.DREAMY,
}


# === 무드 → 장르 매핑 ===
_MOOD_TO_GENRES: dict[Mood, list[str]] = {
    Mood.COZY: ["에세이", "소설", "시", "힐링"],
    Mood.ADVENTUROUS: ["판타지", "SF", "여행", "모험"],
    Mood.REFLECTIVE: ["인문학", "철학", "심리학", "자기계발"],
    Mood.DREAMY: ["시", "판타지", "로맨스", "예술"],
    Mood.THRILLING: ["미스터리", "스릴러", "추리", "공포"],
    Mood.CALM: ["에세이", "자기계발", "과학", "역사"],
}


def get_mood(time_of_day: TimeOfDay, weather: WeatherCondition) -> Mood:
    """시간대와 날씨 조합으로 무드를 결정합니다."""
    return _MOOD_TABLE.get((time_of_day, weather), Mood.CALM)


def get_genres_for_mood(mood: Mood) -> list[str]:
    """무드에 어울리는 장르 목록을 반환합니다."""
    return _MOOD_TO_GENRES.get(mood, ["소설", "에세이"])


def recommend_genres(hour: int, weather: WeatherCondition) -> tuple[Mood, list[str]]:
    """시간(0~23)과 날씨로 추천 장르를 한번에 결정합니다.

    Returns:
        (무드, 장르 리스트) 튜플
    """
    time_of_day = hour_to_time_of_day(hour)
    mood = get_mood(time_of_day, weather)
    genres = get_genres_for_mood(mood)
    return mood, genres
