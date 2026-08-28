"""사서 캐릭터 레지스트리 (id, name, icon, 역할, 특화 장르).

프론트엔드 데이터와 동기화된 사서 메타데이터를 관리합니다.
switchTo 응답 생성 및 역할 분담 판별에 사용됩니다.

# 역할 분담:
# - cat(블루): 친근한 반말(~냥) 말투. 전 장르 추천 가능하며 미스터리·추리·탐정·스릴러에 특화
# - stork(슈빌): 차분하고 정중한 존댓말(공손체). 전 장르 추천 가능하며 비즈니스·경영·경제·투자에 특화
# (두 사서 모두 날씨·시간대·기분 정보를 대화와 추천에 활용)
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LibrarianInfo:
    """사서 캐릭터 메타데이터."""

    id: str
    name: str
    icon: str
    role: str  # 역할 요약
    genre_focus: str = ""  # 특화 장르 (signals에 전달)
    specialties: list[str] = field(default_factory=list)  # 특화 영역 키워드


# === 사서 레지스트리 ===

CAT = LibrarianInfo(
    id="cat",
    name="고양이 사서",
    icon="🐱",
    role="미스터리·추리 도서 특화 및 친근한 반말 상담 (~냥)",
    genre_focus="미스터리",
    specialties=["미스터리", "추리", "소설", "에세이", "스릴러", "힐링", "시"],
)

STORK = LibrarianInfo(
    id="stork",
    name="황새 사서",
    icon="🪿",
    role="비즈니스·경영·경제 도서 특화 및 정중한 지적 상담",
    genre_focus="비즈니스",
    specialties=["비즈니스", "경영", "경제", "투자", "자기계발", "SF", "과학", "역사"],
)

# id로 빠르게 조회할 수 있는 맵
LIBRARIAN_REGISTRY: dict[str, LibrarianInfo] = {
    CAT.id: CAT,
    STORK.id: STORK,
}


def get_librarian(librarian_id: str) -> LibrarianInfo | None:
    """id로 사서 정보를 조회합니다. 없으면 None 반환."""
    return LIBRARIAN_REGISTRY.get(librarian_id)


def get_other_librarian(current_id: str) -> LibrarianInfo | None:
    """현재 사서가 아닌 다른 사서 정보를 반환합니다 (switchTo 생성용)."""
    if current_id == "cat":
        return STORK
    if current_id == "stork":
        return CAT
    return CAT  # 기본 폴백
