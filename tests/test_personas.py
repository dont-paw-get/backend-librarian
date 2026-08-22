"""페르소나 프롬프트 테스트."""

from app.librarian.personas.base import COMMON_RULES, build_system_prompt
from app.librarian.personas.cat import CAT_CHARACTER_PROMPT, get_cat_system_prompt


class TestCommonRules:
    def test_contains_librarian_identity(self):
        assert "사서" in COMMON_RULES

    def test_contains_emoji_rule(self):
        assert "이모지" in COMMON_RULES

    def test_contains_korean_rule(self):
        assert "한국어" in COMMON_RULES

    def test_contains_switch_rule(self):
        assert "다른 사서" in COMMON_RULES


class TestBuildSystemPrompt:
    def test_combines_character_and_common(self):
        character = "# 테스트 캐릭터\n테스트 규칙"
        result = build_system_prompt(character)
        assert "테스트 캐릭터" in result
        assert "공통 규칙" in result


class TestCatPersona:
    def test_cat_prompt_has_identity(self):
        assert "러시안 블루" in CAT_CHARACTER_PROMPT
        assert "나비" in CAT_CHARACTER_PROMPT

    def test_cat_prompt_has_speech_rules(self):
        assert "냥" in CAT_CHARACTER_PROMPT

    def test_cat_prompt_has_genres(self):
        assert "소설" in CAT_CHARACTER_PROMPT
        assert "에세이" in CAT_CHARACTER_PROMPT

    def test_cat_prompt_has_switch_guidance(self):
        assert "황새 사서" in CAT_CHARACTER_PROMPT
        assert "switchTo" in CAT_CHARACTER_PROMPT

    def test_full_prompt_includes_common_rules(self):
        full = get_cat_system_prompt()
        # 캐릭터 부분
        assert "나비" in full
        assert "냥" in full
        # 공통 규칙 부분
        assert "공통 규칙" in full
        assert "한국어" in full

    def test_full_prompt_is_not_empty(self):
        full = get_cat_system_prompt()
        assert len(full) > 500  # 충분히 구체적인 프롬프트인지
