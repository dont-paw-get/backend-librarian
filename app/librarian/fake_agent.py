"""프론트 연동 테스트용 fake 에이전트 응답기.

Bedrock 연동 전까지 사용합니다.
사용자 메시지를 키워드 분석하여:
1. 프롬프트 유출 시도 → 거부
2. 다른 사서 담당 장르 → switchTo 유도 응답 (황새 사서 언급)
3. 특정 장르 키워드 → 해당 장르에서 추천
4. 기본 → 무드 기반 랜덤 추천
"""

import random

from app.librarian.librarians import CAT, STORK

# === 키워드 매핑 ===

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

# 황새 사서 담당 장르 키워드 → switchTo 유도
_STORK_GENRE_KEYWORDS: dict[str, str] = {
    "미스터리": "미스터리",
    "추리": "미스터리",
    "탐정": "미스터리",
    "판타지": "판타지",
    "마법": "판타지",
    "이세계": "판타지",
    "sf": "SF",
    "공상과학": "SF",
    "우주": "SF",
    "여행": "여행",
    "배낭여행": "여행",
    "과학": "과학",
    "물리": "과학",
    "생물": "과학",
    "역사": "역사",
    "전쟁": "역사",
    "고대": "역사",
}

# cat 사서 담당 장르 키워드
_CAT_GENRE_KEYWORDS: dict[str, str] = {
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
    "힐링": "에세이",
    "위로": "에세이",
    "슬픈": "소설",
    "슬플": "소설",
    "감동": "소설",
    "로맨스": "소설",
    "사랑": "소설",
}

# 무드별 도입부 템플릿
_MOOD_INTROS: dict[str, list[str]] = {
    "cozy": [
        "아늑한 분위기에 딱 맞는 책을 찾았다냥 📖",
        "이런 날엔 따뜻한 차 한 잔이랑 책이 최고다냥 ☕",
        "포근한 이불 속에서 읽기 좋은 책이 있다냥 🐾",
    ],
    "adventurous": [
        "오늘은 모험이 하고 싶은 날이다냥! ⚡",
        "활기찬 하루에 어울리는 책을 골라봤다냥 🌟",
        "신나는 이야기가 생각나는 날이다냥 😺",
    ],
    "reflective": [
        "조용히 생각에 잠기기 좋은 날이다냥 🌙",
        "마음을 들여다보기 좋은 책이 있다냥 📚",
        "깊이 있는 글이 어울리는 시간이다냥 🐱",
    ],
    "dreamy": [
        "몽환적인 분위기에 빠져보자냥 ✨",
        "꿈결 같은 이야기를 찾았다냥 💫",
        "감성이 풍부해지는 날이다냥 🌸",
    ],
    "thrilling": [
        "두근두근 긴장감 넘치는 책을 추천할게냥! 🔥",
        "스릴 있는 밤을 보내고 싶다면 이 책이다냥 😼",
        "심장이 빨라지는 이야기가 있다냥 ⚡",
    ],
    "calm": [
        "평온한 마음으로 읽기 좋은 책이다냥 🍃",
        "여유로운 시간에 딱인 책을 골랐다냥 ☀️",
        "차분하게 한 장씩 넘기기 좋은 날이다냥 📖",
    ],
}

# 장르별 추천 도서 (제목, 저자) — 데모용 고정 목록
_GENRE_BOOKS: dict[str, list[tuple[str, str]]] = {
    "소설": [
        ("달러구트 꿈 백화점", "이미예"),
        ("아몬드", "손원평"),
        ("불편한 편의점", "김호연"),
    ],
    "에세이": [
        ("하마터면 열심히 살 뻔했다", "하완"),
        ("죽고 싶지만 떡볶이는 먹고 싶어", "백세희"),
        ("나는 나로 살기로 했다", "김수현"),
    ],
    "시": [
        ("너에게 가려고 바람이 분다", "이정하"),
        ("흔들리며 피는 꽃", "도종환"),
        ("모든 순간이 너였다", "하태완"),
    ],
    "자기계발": [
        ("원씽", "게리 켈러"),
        ("아주 작은 습관의 힘", "제임스 클리어"),
        ("역행자", "자청"),
    ],
    "심리학": [
        ("생각에 관한 생각", "대니얼 카너먼"),
        ("미움받을 용기", "기시미 이치로"),
        ("관계의 재발견", "존 가트맨"),
    ],
    "인문학": [
        ("사피엔스", "유발 하라리"),
        ("총, 균, 쇠", "재레드 다이아몬드"),
        ("정의란 무엇인가", "마이클 샌델"),
    ],
}


def _detect_injection(message: str) -> bool:
    """프롬프트 유출/악의적 시도를 감지합니다."""
    msg_lower = message.lower()
    return any(keyword in msg_lower for keyword in _INJECTION_KEYWORDS)


def _detect_stork_genre(message: str) -> str | None:
    """메시지에서 황새 사서 담당 장르 키워드를 감지합니다."""
    msg_lower = message.lower()
    for keyword, genre in _STORK_GENRE_KEYWORDS.items():
        if keyword in msg_lower:
            return genre
    return None


def _detect_cat_genre(message: str) -> str | None:
    """메시지에서 고양이 사서 담당 장르 키워드를 감지합니다."""
    msg_lower = message.lower()
    for keyword, genre in _CAT_GENRE_KEYWORDS.items():
        if keyword in msg_lower:
            return genre
    return None


async def fake_cat_agent(message: str, context: dict) -> str:
    """fake cat 에이전트 — 키워드 분석 + 무드/장르 기반 고양이 말투 응답 생성.

    Args:
        message: 사용자 메시지
        context: handle_chat이 조립한 맥락 (mood, recommended_genres 등)

    Returns:
        고양이 말투 응답 텍스트
    """
    # 1. 프롬프트 유출 시도 → 거부
    if _detect_injection(message):
        return (
            "어머, 그건 나의 비밀이다냥! 🙀\n\n"
            "나는 책 추천해주는 사서 고양이라냥~ "
            "읽고 싶은 책 장르나 오늘 기분을 말해주면 "
            "딱 맞는 책을 찾아줄 수 있다냥 📚🐾"
        )

    # 2. 황새 사서 담당 장르 → switchTo 유도
    stork_genre = _detect_stork_genre(message)
    if stork_genre:
        return (
            f"오호, {stork_genre} 장르에 관심이 있구냥! 🐾\n\n"
            f"사실 그 분야는 우리 {STORK.name}가 훨씬 잘 알고 있다냥~ 🪿 "
            f"{STORK.name}는 {', '.join(STORK.genres[:3])} 같은 장르의 전문가라냥!\n\n"
            f"내가 {STORK.name}한테 연결해줄게냥~ 😺"
        )

    # 3. cat 담당 장르 키워드 감지 → 해당 장르에서 추천
    cat_genre = _detect_cat_genre(message)
    mood = context.get("mood", "calm")
    intros = _MOOD_INTROS.get(mood, _MOOD_INTROS["calm"])
    intro = random.choice(intros)

    if cat_genre:
        chosen_genre = cat_genre
    else:
        # 4. 기본: 무드 기반 추천 장르에서 선택
        genres = context.get("recommended_genres", ["소설", "에세이"])
        # cat 담당 장르만 필터링
        cat_genres = [g for g in genres if g in _GENRE_BOOKS]
        chosen_genre = random.choice(cat_genres) if cat_genres else "소설"

    books = _GENRE_BOOKS.get(chosen_genre, _GENRE_BOOKS["소설"])
    book_title, book_author = random.choice(books)

    # 응답 조합
    response = (
        f"{intro}\n\n"
        f"오늘 무드에 맞춰서 [{chosen_genre}] 장르의 "
        f"«{book_title}»({book_author})을 추천하고 싶다냥! "
        f"이 책은 지금 같은 분위기에서 읽으면 마음에 꼭 맞을 거다냥 🐾\n\n"
        f"혹시 다른 장르나 분위기가 궁금하면 편하게 말해달라냥~ 😺"
    )

    return response

# === Stork (황새) fake agent ===

# 황새 사서 담당 장르 도서 목록
_STORK_GENRE_BOOKS: dict[str, list[tuple[str, str]]] = {
    "미스터리": [
        ("셜록 홈즈 전집", "코난 도일"),
        ("용의자 X의 헌신", "히가시노 게이고"),
        ("종이 여자", "기욤 뮈소"),
    ],
    "판타지": [
        ("해리 포터", "J.K. 롤링"),
        ("반지의 제왕", "J.R.R. 톨킨"),
        ("나미야 잡화점의 기적", "히가시노 게이고"),
    ],
    "SF": [
        ("프로젝트 헤일메리", "앤디 위어"),
        ("파운데이션", "아이작 아시모프"),
        ("멋진 신세계", "올더스 헉슬리"),
    ],
    "여행": [
        ("나의 문화유산답사기", "유홍준"),
        ("여행의 이유", "김영하"),
        ("걷는 사람, 하정우", "하정우"),
    ],
    "과학": [
        ("코스모스", "칼 세이건"),
        ("이기적 유전자", "리처드 도킨스"),
        ("엘레강스", "이안 스튜어트"),
    ],
    "역사": [
        ("역사의 역사", "유시민"),
        ("나의 한국현대사", "유시민"),
        ("세계사를 바꾼 12가지 신소재", "사토 겐타로"),
    ],
}

# 무드별 도입부 (황새 말투)
_STORK_MOOD_INTROS: dict[str, list[str]] = {
    "cozy": [
        "비가 내리는 날엔, 미스터리 한 권이 잘 어울린답니다 🌧️",
        "포근한 분위기에 어울리는 책을 찾아드릴게요 📚",
        "이런 날엔 따뜻한 이야기 속으로 빠져보시는 건 어떨까요 ✨",
    ],
    "adventurous": [
        "맑은 하늘 아래선 모험이 기다리고 있답니다 ☀️",
        "활기찬 날씨에 어울리는 책을 골라봤어요 🪿",
        "오늘 같은 날엔 새로운 세계로 떠나보시지요 🌟",
    ],
    "reflective": [
        "고요한 시간엔 깊이 있는 이야기가 어울린답니다 🌙",
        "생각이 깊어지는 날이군요. 좋은 책을 추천드릴게요 📖",
        "이런 분위기엔 지적 탐험을 떠나보시는 건 어떨지요 🪿",
    ],
    "dreamy": [
        "몽환적인 날씨에는 판타지가 잘 어울린답니다 ✨",
        "꿈결 같은 분위기에 빠져들 책을 찾았어요 💫",
        "호호, 이런 날엔 상상의 세계가 더 가깝게 느껴지지요 🌸",
    ],
    "thrilling": [
        "거친 바람이 부는 날엔, 스릴 넘치는 이야기가 제격이랍니다 ⚡",
        "긴장감 가득한 책을 추천드릴게요 🔥",
        "이 날씨엔 심장이 뛰는 이야기가 어울린답니다 🪿",
    ],
    "calm": [
        "평온한 하늘 아래, 여유로운 독서를 추천드려요 🌤️",
        "차분한 오늘엔 세상을 넓히는 책이 어떨까요 📚",
        "호호, 좋은 날씨에는 좋은 책이 함께해야지요 🪿",
    ],
}

# 날씨별 추천 이유 멘트
_WEATHER_REASONS: dict[str, str] = {
    "clear": "맑은 날씨처럼 시야가 넓어지는",
    "cloudy": "흐린 하늘 아래 집중하기 좋은",
    "rainy": "비 소리를 배경음악 삼아 읽기 좋은",
    "snowy": "눈 내리는 창밖을 바라보며 빠져들",
    "stormy": "폭풍우처럼 강렬한 몰입감을 주는",
    "foggy": "안개 속 미지의 세계 같은",
}

# cat 사서 담당 장르 키워드 (stork 기준에서)
_CAT_GENRE_KEYWORDS_FOR_STORK: dict[str, str] = {
    "소설": "소설",
    "에세이": "에세이",
    "수필": "에세이",
    "시": "시",
    "시집": "시",
    "자기계발": "자기계발",
    "심리": "심리학",
    "심리학": "심리학",
    "인문": "인문학",
    "인문학": "인문학",
    "힐링": "에세이",
    "위로": "에세이",
}


def _detect_cat_genre_for_stork(message: str) -> str | None:
    """메시지에서 고양이 사서 담당 장르 키워드를 감지 (stork 관점)."""
    msg_lower = message.lower()
    for keyword, genre in _CAT_GENRE_KEYWORDS_FOR_STORK.items():
        if keyword in msg_lower:
            return genre
    return None


async def fake_stork_agent(message: str, context: dict) -> str:
    """fake stork 에이전트 — 날씨/무드 특화 황새 말투 응답 생성.

    Args:
        message: 사용자 메시지
        context: handle_chat이 조립한 맥락 (mood, recommended_genres, weather 등)

    Returns:
        황새 말투 응답 텍스트
    """
    # 1. 프롬프트 유출 시도 → 거부
    if _detect_injection(message):
        return (
            "호호, 그건 사서의 비밀이랍니다 🪿\n\n"
            "저는 날씨와 분위기에 맞는 책을 추천해드리는 황새 사서예요. "
            "오늘의 날씨나 읽고 싶은 분위기를 말씀해주시면 "
            "딱 맞는 책을 찾아드릴게요 📚✨"
        )

    # 2. 고양이 사서 담당 장르 → switchTo 유도
    cat_genre = _detect_cat_genre_for_stork(message)
    if cat_genre:
        return (
            f"아, {cat_genre} 장르에 관심이 있으시군요 🪿\n\n"
            f"그 분야는 우리 {CAT.name} 나비가 더 잘 알고 있답니다 🐱 "
            f"{CAT.name}는 {', '.join(CAT.genres[:3])} 같은 장르의 전문가이지요!\n\n"
            f"제가 {CAT.name}에게 연결해드릴게요~ ✨"
        )

    # 3. 날씨/무드 기반 추천
    mood = context.get("mood", "calm")
    weather_info = context.get("weather", {})
    weather_condition = weather_info.get("condition", "clear")
    temperature = weather_info.get("temperature")

    intros = _STORK_MOOD_INTROS.get(mood, _STORK_MOOD_INTROS["calm"])
    intro = random.choice(intros)

    # 무드에 맞는 장르 선택 (stork 담당만)
    genres = context.get("recommended_genres", ["미스터리", "판타지"])
    stork_genres = [g for g in genres if g in _STORK_GENRE_BOOKS]
    chosen_genre = random.choice(stork_genres) if stork_genres else "미스터리"

    books = _STORK_GENRE_BOOKS.get(chosen_genre, _STORK_GENRE_BOOKS["미스터리"])
    book_title, book_author = random.choice(books)

    weather_reason = _WEATHER_REASONS.get(weather_condition, "분위기에 어울리는")

    # 날씨 정보가 있으면 포함
    weather_mention = ""
    if temperature is not None:
        weather_mention = f"지금 기온이 {temperature}°C인데요, "

    response = (
        f"{intro}\n\n"
        f"{weather_mention}{weather_reason} [{chosen_genre}] 장르의 "
        f"«{book_title}»({book_author})을 추천드리고 싶어요. "
        f"이 책은 오늘 같은 분위기에서 읽으시면 더욱 깊이 빠져드실 수 있을 거랍니다 🪿\n\n"
        f"다른 장르나 분위기가 궁금하시면 편하게 말씀해주세요~ 📚"
    )

    return response
