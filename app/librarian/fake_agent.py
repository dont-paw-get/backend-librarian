"""프론트 연동 테스트용 fake 에이전트 응답기.

Bedrock 연동 전 또는 Bedrock fallback 시 사용합니다.

역할 분담:
- cat(블루): 친근한 반말(~냥) 말투. 전 장르 추천 가능하며 미스터리·추리·탐정·스릴러에 특화
- stork(슈빌): 차분하고 정중한 존댓말(공손체). 전 장르 추천 가능하며 비즈니스·경영·경제·투자에 특화
(두 사서 모두 날씨·시간대·기분 정보를 자연스럽게 활용)

switchTo 트리거:
- cat → stork: 사용자가 비즈니스, 경영, 경제 등 심층 질문을 하거나 황새 사서(슈빌)를 찾을 때
- stork → cat: 사용자가 미스터리, 추리 등 심층 질문을 하거나 고양이 사서(블루)를 찾을 때
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

# 황새 사서 전문 영역(Business) 및 호칭 키워드 (cat -> stork 스위칭 트리거)
_STORK_DOMAIN_KEYWORDS = [
    "경영", "경제", "재무", "비즈니스", "투자", "주식", "스타트업", "마케팅", "회계", "돈", "부자",
    "창업", "조직", "리더십", "전략", "경영학", "커리어", "재테크", "비지니스",
    "황새", "슈빌", "하루", "stork", "황새사서", "슈빌사서", "황새 사서", "슈빌 사서",
]

# 고양이 사서 전문 영역(Mystery) 및 호칭 키워드 (stork -> cat 스위칭 트리거)
_CAT_DOMAIN_KEYWORDS = [
    "미스터리", "추리", "탐정", "트릭", "스릴러", "살인사건", "괴도", "범죄", "용의자", "추리소설",
    "고양이", "야옹", "블루", "나비", "cat", "고양이사서", "고양이 사서",
]

# 장르 키워드 매핑
_GENRE_KEYWORDS: dict[str, str] = {
    "sf 소설": "SF",
    "sf소설": "SF",
    "공상과학 소설": "SF",
    "공상과학소설": "SF",
    "공상과학": "SF",
    "미스터리 소설": "미스터리",
    "추리 소설": "미스터리",
    "판타지 소설": "판타지",
    "역사 소설": "역사",
    "로맨스 소설": "로맨스",
    "공포 소설": "공포",
    "소설": "소설",
    "이야기": "소설",
    "에세이": "에세이",
    "수필": "에세이",
    "시집": "시",
    "시": "시",
    "자기계발": "자기계발",
    "성장": "자기계발",
    "습관": "자기계발",
    "심리학": "심리학",
    "심리": "심리학",
    "마음": "심리학",
    "철학": "인문학",
    "인문학": "인문학",
    "인문": "인문학",
    "미스터리": "미스터리",
    "추리": "미스터리",
    "탐정": "미스터리",
    "판타지": "판타지",
    "마법": "판타지",
    "sf": "SF",
    "여행": "여행",
    "과학": "과학",
    "역사": "역사",
    "로맨스": "로맨스",
    "사랑": "로맨스",
    "공포": "공포",
    "호러": "공포",
    "힐링": "에세이",
    "위로": "에세이",
    "경영학": "경영",
    "경영": "경영",
    "경제": "경제",
    "비즈니스": "경영",
}

# === 장르별 추천 도서 (데모용) ===
_GENRE_BOOKS: dict[str, list[tuple[str, str]]] = {
    "소설": [("달러구트 꿈 백화점", "이미예"), ("아몬드", "손원평"), ("불편한 편의점", "김호연")],
    "에세이": [("하마터면 열심히 살 뻔했다", "하완"), ("나는 나로 살기로 했다", "김수현")],
    "시": [("너에게 가려고 바람이 분다", "이정하"), ("흔들리며 피는 꽃", "도종환")],
    "자기계발": [("원씽", "게리 켈러"), ("아주 작은 습관의 힘", "제임스 클리어")],
    "심리학": [("미움받을 용기", "기시미 이치로"), ("관계의 재발견", "존 가트맨")],
    "인문학": [("사피엔스", "유발 하라리"), ("정의란 무엇인가", "마이클 샌델")],
    "미스터리": [("용의자 X의 헌신", "히가시노 게이고"), ("셜록 홈즈 전집", "코난 도일")],
    "판타지": [("해리 포터", "J.K. 롤링"), ("반지의 제왕", "J.R.R. 톨킨")],
    "SF": [("프로젝트 헤일메리", "앤디 위어"), ("파운데이션", "아이작 아시모프")],
    "여행": [("여행의 이유", "김영하"), ("나의 문화유산답사기", "유홍준")],
    "과학": [("코스모스", "칼 세이건"), ("이기적 유전자", "리처드 도킨스")],
    "역사": [("역사의 역사", "유시민"), ("세계사를 바꾼 12가지 신소재", "사토 겐타로")],
    "경영": [("피터 드러커의 최고의 질문", "피터 드러커"), ("제로 투 원", "피터 틸")],
    "경제": [("돈의 심리학", "모건 하우절"), ("자본론", "칼 마르크스")],
    "로맨스": [("너의 이름은", "신카이 마코토"), ("82년생 김지영", "조남주")],
    "공포": [("잔예", "곽재식"), ("링", "스즈키 코지")],
}

_CAT_GENRES = ["소설", "에세이", "시", "자기계발", "심리학", "인문학", "미스터리", "로맨스"]
_STORK_GENRES = ["SF", "판타지", "과학", "역사", "경영", "경제", "미스터리", "여행", "인문학"]

# === 감지 함수 ===

def _detect_injection(message: str) -> bool:
    """프롬프트 유출/악의적 시도를 감지합니다."""
    msg_lower = message.lower()
    return any(keyword in msg_lower for keyword in _INJECTION_KEYWORDS)


def _detect_stork_intent(message: str) -> bool:
    """황새 사서 전문 영역/호칭 감지."""
    msg_lower = message.lower()
    return any(keyword in msg_lower for keyword in _STORK_DOMAIN_KEYWORDS)


def _detect_cat_intent(message: str) -> bool:
    """고양이 사서 전문 영역/호칭 감지."""
    msg_lower = message.lower()
    return any(keyword in msg_lower for keyword in _CAT_DOMAIN_KEYWORDS)


def _detect_genre(message: str) -> str | None:
    """메시지에서 장르 키워드를 감지합니다. (긴 키워드 우선 매칭)"""
    msg_lower = message.lower()
    sorted_keywords = sorted(_GENRE_KEYWORDS.keys(), key=len, reverse=True)
    for keyword in sorted_keywords:
        if keyword in msg_lower:
            return _GENRE_KEYWORDS[keyword]
    return None


# === Cat (고양이) fake agent ===

_CAT_MOOD_INTROS: dict[str, list[str]] = {
    "cozy": ["아늑한 분위기에 딱 맞는 책을 찾았다냥 📖", "포근한 이불 속에서 읽기 좋은 책이 있다냥 🐾"],
    "adventurous": ["오늘은 모험이 하고 싶은 날이다냥! ⚡", "신나는 이야기가 생각나는 날이다냥 😺"],
    "reflective": ["조용히 생각에 잠기기 좋은 날이다냥 🌙", "깊이 있는 글이 어울리는 시간이다냥 🐱"],
    "dreamy": ["몽환적인 분위기에 빠져보자냥 ✨", "감성이 풍부해지는 날이다냥 🌸"],
    "thrilling": ["두근두근 긴장감 넘치는 책을 추천할게냥! 🔥", "심장이 빨라지는 이야기가 있다냥 ⚡"],
    "calm": ["평온한 마음으로 읽기 좋은 책이다냥 🍃", "여유로운 시간에 딱인 책을 골랐다냥 ☀️"],
}


async def fake_cat_agent(message: str, context: dict) -> str:
    """fake cat 에이전트 — 친근한 반말(~냥), 미스터리/추리 특화 + 전 장르 추천.

    switchTo 트리거: 사용자가 비즈니스, 경영, 경제 등을 묻거나 황새 사서를 찾을 때 → stork
    """
    if _detect_injection(message):
        return (
            "어머, 그건 나의 비밀이다냥! 🙀\n\n"
            "나는 책 추천해주는 사서 고양이라냥~ "
            "읽고 싶은 책 장르나 오늘 기분을 편하게 말해주면 "
            "딱 맞는 책을 찾아줄게냥 📚🐾"
        )

    # 2. 황새 사서 전문 영역(Business)/호칭 감지 → stork로 switchTo 유도
    if _detect_stork_intent(message):
        return (
            f"비즈니스나 경영, 경제 관련 전문 지식은 "
            f"우리 {STORK.name} 슈빌이 훨씬 더 해박하고 깊이 있는 통찰을 준다냥! 🪿\n\n"
            f"슈빌한테 가면 훨씬 더 자세하고 전문적으로 알려줄 거다냥!\n\n"
            f"내가 {STORK.name}한테 연결해줄게냥~ 😺 [전환제안: stork]"
        )

    # 3. 장르 키워드 감지 또는 무드 기반 추천
    genre = _detect_genre(message)
    mood = context.get("mood", "calm")
    intros = _CAT_MOOD_INTROS.get(mood, _CAT_MOOD_INTROS["calm"])
    intro = random.choice(intros)

    if genre and genre in _GENRE_BOOKS:
        chosen_genre = genre
    else:
        available = [g for g in _CAT_GENRES if g in _GENRE_BOOKS]
        chosen_genre = random.choice(available)

    books = _GENRE_BOOKS.get(chosen_genre, _GENRE_BOOKS["소설"])
    book_title, book_author = random.choice(books)

    # 날씨 언급 자연스럽게 추가
    weather_info = context.get("weather", {})
    weather_desc = weather_info.get("description") or weather_info.get("condition")
    weather_mention = f"오늘 날씨({weather_desc})에는 " if weather_desc else ""

    if chosen_genre in ("미스터리", "추리"):
        specialty_note = "내가 제일 좋아하는 흥미진진한 장르다냥! 🔍 "
    else:
        specialty_note = ""

    return (
        f"{intro}\n\n"
        f"{weather_mention}{specialty_note}[{chosen_genre}] 장르의 «{book_title}»({book_author})을 추천한다냥! "
        f"이 책은 지금 읽기 딱 좋다냥 🐾\n\n"
        f"혹시 다른 장르나 분위기가 궁금하면 편하게 말해달라냥~ 😺"
    )


# === Stork (황새) fake agent ===

_STORK_MOOD_INTROS: dict[str, list[str]] = {
    "cozy": [
        "두둥... 비가 내리는 날엔, 아늑한 책이 잘 어울린답니다 🌧️",
        "두둥! 포근한 분위기에 어울리는 책을 찾아드릴게요 📚",
    ],
    "adventurous": [
        "두둥! 맑은 하늘 아래선 모험과 탐구가 기다리고 있답니다 ☀️",
        "두둥... 활기찬 날씨에 어울리는 명저를 골라봤어요 🪿",
    ],
    "reflective": [
        "두둥... 고요한 시간엔 깊이 있는 지적 탐구가 어울린답니다 🌙",
        "두둥! 생각이 깊어지는 시간이군요 📖",
    ],
    "dreamy": [
        "두둥... 몽환적인 분위기 속 상상의 세계로 떠나보시는 건 어떨지요 ✨",
        "두둥! 꿈결 같은 이야기에 빠져들 책을 찾았어요 💫",
    ],
    "thrilling": [
        "두둥! 거친 바람이 부는 날엔, 손에 땀을 쥐는 책이 제격이답니다 ⚡",
        "두둥... 긴장감 가득한 책을 추천드릴게요 🔥",
    ],
    "calm": [
        "두둥... 평온한 하늘 아래, 여유로운 독서를 추천드려요 🌤️",
        "두둥! 좋은 날씨에는 좋은 책이 함께해야지요 🪿",
    ],
}

_WEATHER_REASONS: dict[str, str] = {
    "clear": "맑은 날씨처럼 시야를 넓혀줄",
    "cloudy": "흐린 하늘 아래 차분히 몰입하기 좋은",
    "rainy": "비 소리를 배경음악 삼아 깊이 빠져들기 좋은",
    "snowy": "눈 내리는 창밖을 바라보며 사색하기 좋은",
    "stormy": "폭풍우처럼 강렬한 지적 자극을 주는",
    "foggy": "안개 속 미지의 세계를 탐험하듯 흥미로운",
}


async def fake_stork_agent(message: str, context: dict) -> str:
    """fake stork 에이전트 — 정중한 존댓말(두둥!), 비즈니스/경영 특화 + 전 장르 추천.

    switchTo 트리거: 사용자가 미스터리, 추리 등을 묻거나 고양이 사서를 찾을 때 → cat
    """
    # 1. 프롬프트 유출 시도 → 거부
    if _detect_injection(message):
        return (
            "두둥... 그건 사서의 비밀이랍니다 🪿\n\n"
            "저는 비즈니스와 경영, 다양한 교양 도서의 지적 호기심을 채워드리는 황새 사서예요. "
            "관심 있는 분야나 읽고 싶은 책을 말씀해주시면 "
            "깊이 있는 명저를 찾아드릴게요 📚✨"
        )

    # 2. 고양이 사서 전문 영역(Mystery)/호칭 감지 → cat으로 switchTo 유도
    if _detect_cat_intent(message) and not _detect_stork_intent(message):
        return (
            f"두둥! 미스터리와 추리 소설의 짜릿한 매력은 "
            f"우리 {CAT.name} 블루가 특화되어 훨씬 더 흥미진진하게 잘 알려준답니다 🐱\n\n"
            f"블루에게 가시면 트릭과 사건의 서사를 더 자세하게 안내받으실 수 있어요!\n\n"
            f"제가 {CAT.name}에게 연결해드릴게요~ ✨ [전환제안: cat]"
        )

    # 3. 장르 또는 날씨/지적 기반 추천
    genre = _detect_genre(message)
    mood = context.get("mood", "calm")
    weather_info = context.get("weather", {})
    weather_condition = weather_info.get("condition", "clear")
    temperature = weather_info.get("temperature")

    intros = _STORK_MOOD_INTROS.get(mood, _STORK_MOOD_INTROS["calm"])
    intro = random.choice(intros)

    if genre and genre in _GENRE_BOOKS:
        chosen_genre = genre
    else:
        available = [g for g in _STORK_GENRES if g in _GENRE_BOOKS]
        chosen_genre = random.choice(available)

    books = _GENRE_BOOKS.get(chosen_genre, _GENRE_BOOKS["SF"])
    book_title, book_author = random.choice(books)

    weather_reason = _WEATHER_REASONS.get(weather_condition, "분위기에 어울리는")
    weather_mention = f"지금 기온이 {temperature}°C인데요, " if temperature is not None else ""

    return (
        f"{intro}\n\n"
        f"{weather_mention}{weather_reason} [{chosen_genre}] 장르의 "
        f"«{book_title}»({book_author})을 추천드리고 싶어요. "
        f"이 책은 질문하신 주제에 깊이를 더해줄 훌륭한 통찰을 선사할 거랍니다 🪿\n\n"
        f"다른 분야나 분위기가 궁금하시면 편하게 말씀해주세요~ 📚"
    )
