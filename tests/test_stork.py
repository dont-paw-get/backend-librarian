"""stork 사서 페르소나 테스트."""

from app.librarian.personas.stork import STORK_CHARACTER_PROMPT, get_stork_system_prompt


class TestStorkPersona:
    def test_stork_prompt_has_identity(self):
        assert "넓적부리황새" in STORK_CHARACTER_PROMPT
        assert "하루" in STORK_CHARACTER_PROMPT

    def test_stork_prompt_has_speech_rules(self):
        assert "랍니다" in STORK_CHARACTER_PROMPT

    def test_stork_prompt_has_dudung_signature(self):
        assert "두둥" in STORK_CHARACTER_PROMPT

    def test_stork_prompt_has_weather_focus(self):
        assert "날씨" in STORK_CHARACTER_PROMPT
        assert "시간대" in STORK_CHARACTER_PROMPT

    def test_stork_prompt_has_switch_guidance(self):
        assert "고양이 사서" in STORK_CHARACTER_PROMPT
        assert "switchTo" in STORK_CHARACTER_PROMPT

    def test_full_prompt_includes_common_rules(self):
        full = get_stork_system_prompt()
        assert "하루" in full
        assert "공통 규칙" in full
        assert "한국어" in full

    def test_full_prompt_is_not_empty(self):
        full = get_stork_system_prompt()
        assert len(full) > 500
