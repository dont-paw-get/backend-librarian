"""사서 레지스트리 테스트."""

from app.librarian.librarians import (
    CAT,
    LIBRARIAN_REGISTRY,
    STORK,
    get_librarian,
    get_other_librarian,
)


class TestLibrarianRegistry:
    def test_cat_exists(self):
        assert CAT.id == "cat"
        assert "소설" in CAT.genres

    def test_stork_exists(self):
        assert STORK.id == "stork"
        assert "미스터리" in STORK.genres

    def test_registry_has_two_entries(self):
        assert len(LIBRARIAN_REGISTRY) == 2

    def test_get_librarian_found(self):
        info = get_librarian("cat")
        assert info is not None
        assert info.name == "고양이 사서"

    def test_get_librarian_not_found(self):
        info = get_librarian("unknown")
        assert info is None

    def test_get_other_librarian_from_cat(self):
        other = get_other_librarian("cat")
        assert other is not None
        assert other.id == "stork"

    def test_get_other_librarian_from_stork(self):
        other = get_other_librarian("stork")
        assert other is not None
        assert other.id == "cat"

    def test_get_other_librarian_unknown(self):
        # 존재하지 않는 id면 첫 번째 사서를 반환 (레지스트리에서 자기 아닌 것)
        other = get_other_librarian("unknown")
        assert other is not None
