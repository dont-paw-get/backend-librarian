"""사서 캐릭터 레지스트리 (id, name, icon, genres).

프론트엔드 데이터와 동기화된 사서 메타데이터를 관리합니다.
switchTo 응답 생성 및 담당 장르 판별에 사용됩니다.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LibrarianInfo:
    """사서 캐릭터 메타데이터."""

    id: str
    name: str
    icon: str
    genres: list[str] = field(default_factory=list)


# === 사서 레지스트리 ===

CAT = LibrarianInfo(
    id="cat",
    name="고양이 사서",
    icon="🐱",
    genres=["소설", "에세이", "시", "자기계발", "심리학", "인문학"],
)

STORK = LibrarianInfo(
    id="stork",
    name="황새 사서",
    icon="🪿",
    genres=["미스터리", "판타지", "SF", "여행", "과학", "역사"],
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
