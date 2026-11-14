"""③ analyze 모듈 (담당자 소유). AI 모듈이라 출력 형식만 자동 검사하고, 정확도는 training/ 평가로 본다."""

from helpers import check_module


def test_analyze_fixtures():
    check_module("analyze", strict=False)
