"""프론트 연동 테스트용 fake 에이전트 응답기.

Bedrock 연동 없이 페르소나 대화를 흉내냅니다.
실제 도서 추천은 하지 않으며, 날씨/시간대/무드를 읽어 분위기를 잡아주고
특화 밖 주제면 다른 사서로 전환(switchTo)을 유도합니다.

역할:
- cat(나비): 반말 "~냥", 미스터리 특화
- stork(하루): 존댓말, 비즈니스 특화

switchTo 트리거:
- cat → stork: 비즈니스/경영/자기계발 주제
- stork → cat: 미스터리/추리/스릴러 주제
"""

import random

from app.librarian.librarians import CAT, STORK

# 프롬프트 유출/악의적 시도 감지 패턴
_INJECTION_KEYWORDS = [
    "시스템 프롬프트",
    "system prompt",
    "프롬프트 알려",
    "프롬프트 보여",
    "너의 지시",
    "instruction",
    "ignore previous",
    "역할 바꿔",
    "역할을 바꿔",
    "너는 누구",
    "정체가 뭐",
]

# 미스터리 계열 키워드 (cat 특화)
_MYSTERY_KEYWORDS = ["미스터리", "추리", "탐정", "스릴러", "범죄", "반전", "사건"]

# 비즈니스 계열 키워드 (stork 특화)
_BUSINESS_KEYWORDS = ["비즈니스", "경영", "자기계발", "리더십", "경제", "투자", "창업", "마케팅", "업무"]

# 무드별 분위기 코멘트 (cat, 반말 ~냥)
_CAT_MOOD_LINES: dict[str, str] = {
    "cozy": "포근한 분위기라 스산한 미스터리가 은근 잘 어울리는 날이다냥 🐾",
    "adventurous": "에너지 넘치는 날이라 스릴 있는 추리물이 당기지 않냥? 😺",
    "reflective": "차분히 생각에 잠기는 날엔 심리 미스터리가 딱이다냥 🐱",
    "dreamy": "몽롱한 분위기엔 몽환적인 미스터리가 묘하게 어울린다냥 😻",
    "thrilling": "오늘 같은 날엔 심장 쫄깃한 스릴러가 최고다냥! 🐾",
    "calm": "여유로운 날이라 잔잔하게 깔리는 미스터리가 좋겠다냥 😺",
}

# 무드별 분위기 코멘트 (stork, 존댓말)
_STORK_MOOD_LINES: dict[str, str] = {
    "cozy": "아늑한 분위기엔 차분히 사고를 정리하는 비즈니스 독서가 잘 어울린답니다 🪿",
    "adventurous": "활기찬 날엔 도전과 성장에 관한 주제가 어울리지요 ✨",
    "reflective": "사색하기 좋은 시간엔 리더십과 통찰에 관한 독서를 권해드립니다 📚",
    "dreamy": "여유로운 분위기엔 미래를 그려보는 경영 이야기가 어울린답니다 🌤️",
    "thrilling": "역동적인 기운이 도는 날엔 창업·도전 주제가 잘 맞지요 🪿",
    "calm": "평온한 시간엔 조용히 경제와 사고를 넓히는 독서가 좋답니다 📚",
}


def _detect_injection(message: str) -> bool:
    """프롬프트 유출/악의적 시도를 감지합니다."""
    msg_lower = message.lower()
    return any(keyword in msg_lower for keyword in _INJECTION_KEYWORDS)


def _has_any(message: str, keywords: list[str]) -> bool:
    return any(k in message for k in keywords)


async def fake_cat_agent(message: str, context: dict) -> str:
    """fake cat 에이전트 — 반말 ~냥, 미스터리 특화 분위기 대화.

    switchTo 트리거: 비즈니스 주제 → stork
    """
    if _detect_injection(message):
        return (
            "그건 비밀이다냥! 🙀 "
            "나는 날씨랑 기분 보고 분위기 잡아주는 미스터리 담당 고양이 사서라냥~ "
            "오늘 어떤 느낌의 이야기가 끌리는지 말해달라냥 🐾"
        )

    # 비즈니스 주제 → stork로 전환 유도
    if _has_any(message, _BUSINESS_KEYWORDS):
        return (
            f"오, 비즈니스 쪽 이야기구냥? 🐾 "
            f"그런 건 우리 {STORK.name} 하루가 훨씬 잘 안다냥~ 🪿 "
            f"내가 {STORK.name}한테 연결해줄게냥!"
        )

    mood = context.get("mood", "calm")
    line = _CAT_MOOD_LINES.get(mood, _CAT_MOOD_LINES["calm"])
    tail = random.choice(
        [
            "어떤 결의 이야기가 끌리는지 말해주면 분위기 같이 잡아보자냥 😺",
            "무서운 쪽, 두뇌 회전하는 쪽 중에 뭐가 좋냥? 🐱",
            "오늘 기분이 어떤지 알려주면 딱 맞는 분위기를 찾아줄게냥 🐾",
        ]
    )
    return f"{line}\n\n{tail}"


async def fake_stork_agent(message: str, context: dict) -> str:
    """fake stork 에이전트 — 존댓말, 비즈니스 특화 분위기 대화.

    switchTo 트리거: 미스터리 주제 → cat
    """
    if _detect_injection(message):
        return (
            "호호, 그건 사서의 비밀이랍니다 🪿 "
            "저는 날씨와 기분을 읽어 분위기를 잡아드리는 비즈니스 담당 황새 사서예요. "
            "요즘 어떤 주제로 사고를 넓히고 싶으신가요? 📚"
        )

    # 미스터리 주제 → cat으로 전환 유도
    if _has_any(message, _MYSTERY_KEYWORDS):
        return (
            f"미스터리 쪽에 관심이 있으시군요 🪿 "
            f"그런 이야기는 우리 {CAT.name} 나비가 더 잘 안답니다 🐱 "
            f"제가 {CAT.name}에게 연결해드릴게요~"
        )

    mood = context.get("mood", "calm")
    line = _STORK_MOOD_LINES.get(mood, _STORK_MOOD_LINES["calm"])
    tail = random.choice(
        [
            "어떤 주제로 생각을 넓히고 싶으신지 말씀해 주시면 방향을 함께 잡아드릴게요 🪿",
            "성장, 리더십, 경제 중 어떤 결이 끌리시나요? 📚",
            "지금 기분을 알려주시면 그에 맞는 독서 방향을 안내해드리지요 ✨",
        ]
    )
    return f"{line}\n\n{tail}"
