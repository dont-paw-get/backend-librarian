"""프론트 연동 테스트용 fake 에이전트 응답기.

Bedrock 연동 전까지 사용합니다.

역할 분담:
- cat(나비): 전 장르 추천 (장르/취향 기반)
- stork(하루): 날씨/시간대 기반 큐레이션

switchTo 트리거:
- cat → stork: 사용자가 날씨/시간대 기반 추천을 원할 때
- stork → cat: 사용자가 특정 장르를 콕 집어 요청할 때
"""

import random

from app.librarian.librarians import CAT, STORK

# === 공통 ===

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

# 날씨/시간대 관련 키워드 — 이 키워드가 있으면 stork 영역
_WEATHER_TIME_KEYWORDS = [
    "날씨",
    "비 오는",
    "비오는",
    "눈 오는",
    "눈오는",
    "맑은 날",
    "흐린 날",
    "안개",
    "폭풍",
    "시간대",
    "아침에",
    "저녁에",
    "밤에",
    "새벽에",
    "오늘 같은 날",
    "지금 시간",
    "계절",
    "봄에",
    "여름에",
    "가을에",
    "겨울에",
]

# 장르 키워드 매핑 (전 장르 — cat이 전부 담당)
_ALL_GENRE_KEYWORDS: dict[str, str] = {
    "소설": "소설",
    "이야기": "소설",
    "에세이": "에세이",
    "수필": "에세이",
    "시": "시",
    "시집": "시",
    "자기계발": "자기계발",
    "성장": "자기계발",
    "습관": "자기계발",
    "심리": "심리학",
    "심리학": "심리학",
    "마음": "심리학",
    "철학": "인문학",
    "인문": "인문학",
    "인문학": "인문학",
    "미스터리": "미스터리",
    "추리": "미스터리",
    "탐정": "미스터리",
    "판타지": "판타지",
    "마법": "판타지",
    "sf": "SF",
    "공상과학": "SF",
    "여행": "여행",
    "과학": "과학",
    "역사": "역사",
    "로맨스": "로맨스",
    "사랑": "로맨스",
    "공포": "공포",
    "호러": "공포",
    "힐링": "에세이",
    "위로": "에세이",
    "슬픈": "소설",
    "감동": "소설",
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
    "로맨스": [("너의 이름은", "신카이 마코토"), ("82년생 김지영", "조남주")],
    "공포": [("잔예", "곽재식"), ("링", "스즈키 코지")],
}

# === 감지 함수 ===


def _detect_injection(message: str) -> bool:
    """프롬프트 유출/악의적 시도를 감지합니다."""
    msg_lower = message.lower()
    return any(keyword in msg_lower for keyword in _INJECTION_KEYWORDS)


def _detect_weather_time_intent(message: str) -> bool:
    """메시지에 날씨/시간대 기반 추천 의도가 있는지 감지합니다."""
    msg_lower = message.lower()
    return any(keyword in msg_lower for keyword in _WEATHER_TIME_KEYWORDS)


def _detect_genre(message: str) -> str | None:
    """메시지에서 장르 키워드를 감지합니다. (긴 키워드 우선 매칭)"""
    msg_lower = message.lower()
    # 긴 키워드를 먼저 검사해야 "미스터리 소설"에서 "소설"이 아닌 "미스터리"가 잡힘
    sorted_keywords = sorted(_ALL_GENRE_KEYWORDS.keys(), key=len, reverse=True)
    for keyword in sorted_keywords:
        if keyword in msg_lower:
            return _ALL_GENRE_KEYWORDS[keyword]
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
    """fake cat 에이전트 — 전 장르 추천 (장르/취향 기반).

    switchTo 트리거: 사용자가 날씨/시간대 기반 추천을 원할 때 → stork
    """
    # 1. 프롬프트 유출 시도 → 거부
    if _detect_injection(message):
        return (
            "어머, 그건 나의 비밀이다냥! 🙀\n\n"
            "나는 책 추천해주는 사서 고양이라냥~ "
            "읽고 싶은 책 장르나 오늘 기분을 말해주면 "
            "딱 맞는 책을 찾아줄 수 있다냥 📚🐾"
        )

    # 2. 날씨/시간대 의도 감지 → stork로 switchTo 유도
    if _detect_weather_time_intent(message):
        return (
            f"오호, 날씨나 시간대에 맞는 추천을 원하는구냥! 🐾\n\n"
            f"그런 건 우리 {STORK.name} 하루가 전문이다냥~ 🪿 "
            f"하루는 지금 날씨와 시간대를 읽어서 딱 맞는 책을 골라주거든냥!\n\n"
            f"내가 {STORK.name}한테 연결해줄게냥~ 😺"
        )

    # 3. 장르 키워드 감지 → 해당 장르에서 추천
    genre = _detect_genre(message)
    mood = context.get("mood", "calm")
    intros = _CAT_MOOD_INTROS.get(mood, _CAT_MOOD_INTROS["calm"])
    intro = random.choice(intros)

    if genre:
        chosen_genre = genre
    else:
        # 4. 기본: 무드 기반 추천 장르
        genres = context.get("recommended_genres", ["소설", "에세이"])
        available = [g for g in genres if g in _GENRE_BOOKS]
        chosen_genre = random.choice(available) if available else "소설"

    books = _GENRE_BOOKS.get(chosen_genre, _GENRE_BOOKS["소설"])
    book_title, book_author = random.choice(books)

    return (
        f"{intro}\n\n"
        f"[{chosen_genre}] 장르의 «{book_title}»({book_author})을 추천하고 싶다냥! "
        f"이 책은 지금 기분에 꼭 맞을 거다냥 🐾\n\n"
        f"혹시 다른 장르나 분위기가 궁금하면 편하게 말해달라냥~ 😺"
    )


# === Stork (황새) fake agent ===

_STORK_MOOD_INTROS: dict[str, list[str]] = {
    "cozy": ["비가 내리는 날엔, 아늑한 책이 잘 어울린답니다 🌧️", "포근한 분위기에 어울리는 책을 찾아드릴게요 📚"],
    "adventurous": ["맑은 하늘 아래선 모험이 기다리고 있답니다 ☀️", "활기찬 날씨에 어울리는 책을 골라봤어요 🪿"],
    "reflective": ["고요한 시간엔 깊이 있는 이야기가 어울린답니다 🌙", "생각이 깊어지는 시간이군요 📖"],
    "dreamy": ["몽환적인 날씨에는 상상의 세계가 어울린답니다 ✨", "꿈결 같은 분위기에 빠져들 책을 찾았어요 💫"],
    "thrilling": ["거친 바람이 부는 날엔, 스릴 넘치는 이야기가 제격이랍니다 ⚡", "긴장감 가득한 책을 추천드릴게요 🔥"],
    "calm": ["평온한 하늘 아래, 여유로운 독서를 추천드려요 🌤️", "호호, 좋은 날씨에는 좋은 책이 함께해야지요 🪿"],
}

_WEATHER_REASONS: dict[str, str] = {
    "clear": "맑은 날씨처럼 시야가 넓어지는",
    "cloudy": "흐린 하늘 아래 집중하기 좋은",
    "rainy": "비 소리를 배경음악 삼아 읽기 좋은",
    "snowy": "눈 내리는 창밖을 바라보며 빠져들",
    "stormy": "폭풍우처럼 강렬한 몰입감을 주는",
    "foggy": "안개 속 미지의 세계 같은",
}


async def fake_stork_agent(message: str, context: dict) -> str:
    """fake stork 에이전트 — 날씨/시간대 기반 큐레이션.

    switchTo 트리거: 사용자가 특정 장르를 콕 집어 요청할 때 → cat
    """
    # 1. 프롬프트 유출 시도 → 거부
    if _detect_injection(message):
        return (
            "호호, 그건 사서의 비밀이랍니다 🪿\n\n"
            "저는 날씨와 분위기에 맞는 책을 추천해드리는 황새 사서예요. "
            "오늘의 날씨나 읽고 싶은 분위기를 말씀해주시면 "
            "딱 맞는 책을 찾아드릴게요 📚✨"
        )

    # 2. 장르 콕 집어 요청 + 날씨/시간 의도 없음 → cat으로 switchTo 유도
    genre = _detect_genre(message)
    has_weather_time = _detect_weather_time_intent(message)

    if genre and not has_weather_time:
        return (
            f"아, {genre} 장르에 관심이 있으시군요 🪿\n\n"
            f"장르 기반 추천은 우리 {CAT.name} 나비가 더 잘 알고 있답니다 🐱 "
            f"나비는 모든 장르의 전문가이지요!\n\n"
            f"제가 {CAT.name}에게 연결해드릴게요~ ✨"
        )

    # 3. 날씨/시간 기반 추천
    mood = context.get("mood", "calm")
    weather_info = context.get("weather", {})
    weather_condition = weather_info.get("condition", "clear")
    temperature = weather_info.get("temperature")

    intros = _STORK_MOOD_INTROS.get(mood, _STORK_MOOD_INTROS["calm"])
    intro = random.choice(intros)

    # 무드에 맞는 장르 선택
    genres = context.get("recommended_genres", ["미스터리", "소설"])
    available = [g for g in genres if g in _GENRE_BOOKS]
    chosen_genre = random.choice(available) if available else "소설"

    books = _GENRE_BOOKS.get(chosen_genre, _GENRE_BOOKS["소설"])
    book_title, book_author = random.choice(books)

    weather_reason = _WEATHER_REASONS.get(weather_condition, "분위기에 어울리는")
    weather_mention = f"지금 기온이 {temperature}°C인데요, " if temperature is not None else ""

    return (
        f"{intro}\n\n"
        f"{weather_mention}{weather_reason} [{chosen_genre}] 장르의 "
        f"«{book_title}»({book_author})을 추천드리고 싶어요. "
        f"이 책은 오늘 같은 분위기에서 읽으시면 더욱 깊이 빠져드실 수 있을 거랍니다 🪿\n\n"
        f"다른 분위기가 궁금하시면 편하게 말씀해주세요~ 📚"
    )
