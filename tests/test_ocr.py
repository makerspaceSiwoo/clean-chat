"""① ocr 모듈 (담당자 소유). AI 모듈이라 출력 형식만 자동 검사하고, 정확도는 실측으로 본다."""

import pytest

from clean_chat.core.config import FIXTURES
from helpers import check_module


def test_ocr_fixtures():
    if not (FIXTURES / "ocr" / "images" / "sample_01.png").exists():
        pytest.skip("OCR 테스트 이미지 없음 (fixtures/ocr/images/README.md)")
    check_module("ocr", strict=False)
