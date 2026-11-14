"""② parse 모듈 (담당자 소유). 규칙 모듈이라 fixtures 기대값과 정확히 같아야 한다."""

from helpers import check_module


def test_parse_fixtures():
    check_module("parse", strict=True)
