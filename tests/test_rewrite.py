"""④ rewrite 모듈 (담당자 소유). 생성 모듈이라 출력 형식만 자동 검사한다."""

from helpers import check_module


def test_rewrite_fixtures():
    check_module("rewrite", strict=False)
