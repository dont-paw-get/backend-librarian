"""사서 캐릭터 레지스트리 (id, name, icon, 역할, 특화 장르).

프론트엔드 데이터와 동기화된 사서 메타데이터를 관리합니다.
switchTo 응답 생성 및 역할 분담 판별에 사용됩니다.

역할 분담 (실제 도서 추천은 팀원의 검색 에이전트가 담당):
- cat(나비): 반말 "~냥", 친근·사교적, 미스터리 특화. 날씨/시간대/기분 분위기를 잡아줌
- stork(하루): 존댓말·공손, 차분·정중, 비즈니스 특화. 날씨/시간대/기분 분위기를 잡아줌
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LibrarianInfo:
    """사서 캐릭터 메타데이터."""

    id: str
    name: str
    icon: str
    role: str  # 역할 요약
    genre_focus: str  # 특화 장르 (signals에 전달)
    specialties: list[str] = field(default_factory=list)  # 특화 영역 키워드


# === 사서 레지스트리 ===

CAT = LibrarianInfo(
    id="cat",
    name="고양이 사서",
    icon="🐱",
    role="미스터리 특화 · 날씨/시간대/기분 분위기 큐레이션",
    genre_focus="미스터리",
    specialties=["미스터리", "추리", "스릴러", "범죄", "탐정"],
)

STORK = LibrarianInfo(
    id="stork",
    name="황새 사서",
    icon="🪿",
    role="비즈니스 특화 · 날씨/시간대/기분 분위기 큐레이션",
    genre_focus="비즈니스",
    specialties=["비즈니스", "경영", "자기계발", "리더십", "경제"],
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
