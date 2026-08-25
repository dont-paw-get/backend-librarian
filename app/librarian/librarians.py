"""사서 캐릭터 레지스트리 (id, name, icon, 역할).

프론트엔드 데이터와 동기화된 사서 메타데이터를 관리합니다.
switchTo 응답 생성 및 역할 분담 판별에 사용됩니다.

역할 분담:
- cat(나비): 전 장르 도서 추천 (사용자 취향/장르 기반)
- stork(하루): 날씨·시간대 기반 큐레이션 (Open-Meteo + 무드 매핑)
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LibrarianInfo:
    """사서 캐릭터 메타데이터."""

    id: str
    name: str
    icon: str
    role: str  # 역할 요약
    specialties: list[str] = field(default_factory=list)  # 전문 영역 키워드


# === 사서 레지스트리 ===

CAT = LibrarianInfo(
    id="cat",
    name="고양이 사서",
    icon="🐱",
    role="전 장르 도서 추천 (취향/장르 기반)",
    specialties=["장르 추천", "취향 분석", "독서 목록", "감정 기반 추천"],
)

STORK = LibrarianInfo(
    id="stork",
    name="황새 사서",
    icon="🪿",
    role="날씨·시간대 기반 큐레이션",
    specialties=["날씨 추천", "시간대 추천", "분위기 큐레이션", "계절 추천"],
)

# id로 빠르게 조회할 수 있는 맵
LIBRARIAN_REGISTRY: dict[str, LibrarianInfo] = {
    CAT.id: CAT,
    STORK.id: STORK,
}


def get_librarian(librarian_id: str) -> LibrarianInfo | None:
    """id로 사서 메타데이터를 조회합니다."""
    return LIBRARIAN_REGISTRY.get(librarian_id)


def get_other_librarian(current_id: str) -> LibrarianInfo | None:
    """현재 사서가 아닌 다른 사서를 반환합니다."""
    for lid, info in LIBRARIAN_REGISTRY.items():
        if lid != current_id:
            return info
    return None
