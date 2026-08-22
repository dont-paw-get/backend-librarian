"""시간대·날씨 → 무드 → 장르 매핑 로직 테스트."""

import pytest

from app.librarian.curation.mood import (
    Mood,
    TimeOfDay,
    WeatherCondition,
    get_genres_for_mood,
    get_mood,
    hour_to_time_of_day,
    recommend_genres,
)


class TestHourToTimeOfDay:
    @pytest.mark.parametrize(
        ("hour", "expected"),
        [
            (5, TimeOfDay.DAWN),
            (8, TimeOfDay.DAWN),
            (9, TimeOfDay.DAY),
            (12, TimeOfDay.DAY),
            (16, TimeOfDay.DAY),
            (17, TimeOfDay.EVENING),
            (20, TimeOfDay.EVENING),
            (21, TimeOfDay.NIGHT),
            (0, TimeOfDay.NIGHT),
            (3, TimeOfDay.NIGHT),
            (4, TimeOfDay.NIGHT),
        ],
    )
    def test_boundary_hours(self, hour: int, expected: TimeOfDay):
        assert hour_to_time_of_day(hour) == expected


class TestGetMood:
    def test_rainy_evening_is_cozy(self):
        assert get_mood(TimeOfDay.EVENING, WeatherCondition.RAINY) == Mood.COZY

    def test_clear_day_is_adventurous(self):
        assert get_mood(TimeOfDay.DAY, WeatherCondition.CLEAR) == Mood.ADVENTUROUS

    def test_stormy_night_is_thrilling(self):
        assert get_mood(TimeOfDay.NIGHT, WeatherCondition.STORMY) == Mood.THRILLING

    def test_snowy_dawn_is_dreamy(self):
        assert get_mood(TimeOfDay.DAWN, WeatherCondition.SNOWY) == Mood.DREAMY

    def test_foggy_evening_is_dreamy(self):
        assert get_mood(TimeOfDay.EVENING, WeatherCondition.FOGGY) == Mood.DREAMY

    def test_clear_night_is_reflective(self):
        assert get_mood(TimeOfDay.NIGHT, WeatherCondition.CLEAR) == Mood.REFLECTIVE

    @pytest.mark.parametrize("time", list(TimeOfDay))
    @pytest.mark.parametrize("weather", list(WeatherCondition))
    def test_all_combinations_return_valid_mood(self, time: TimeOfDay, weather: WeatherCondition):
        mood = get_mood(time, weather)
        assert mood in Mood


class TestGetGenresForMood:
    def test_cozy_genres(self):
        genres = get_genres_for_mood(Mood.COZY)
        assert "에세이" in genres
        assert "소설" in genres

    def test_thrilling_genres(self):
        genres = get_genres_for_mood(Mood.THRILLING)
        assert "미스터리" in genres
        assert "스릴러" in genres

    def test_all_moods_have_genres(self):
        for mood in Mood:
            genres = get_genres_for_mood(mood)
            assert len(genres) > 0


class TestRecommendGenres:
    def test_rainy_evening_returns_cozy_genres(self):
        mood, genres = recommend_genres(19, WeatherCondition.RAINY)
        assert mood == Mood.COZY
        assert "에세이" in genres

    def test_clear_morning_returns_adventurous(self):
        mood, genres = recommend_genres(10, WeatherCondition.CLEAR)
        assert mood == Mood.ADVENTUROUS
        assert "판타지" in genres

    def test_midnight_storm_returns_thrilling(self):
        mood, genres = recommend_genres(0, WeatherCondition.STORMY)
        assert mood == Mood.THRILLING
        assert "미스터리" in genres
